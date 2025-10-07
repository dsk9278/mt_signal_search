# -*- coding: utf-8 -*-
"""CSV importers for signals and box connections.

- CSVSignalImporter: テンプレ `signal_id, signal_type, ... , logic_expr` を読み込む
- CSVBoxConnImporter: テンプレ `from_box_name, ... , to_box_name` を読み込む

UI には依存しない純粋な I/O レイヤ。例外は上位で拾いやすいように必要最小限のみ捕捉。
`progress_cb` と `cancel_cb` はワーカー(QThread)側から渡せるよう任意引数にしている。
"""

# -----------------------------------------------------------------------------
# このモジュールの位置付け / ワーカー層・UI層との関係
# -----------------------------------------------------------------------------
# - ここは I/O 層（ファイル→ドメインモデル）に徹する。
# - UI はこのモジュールを直接は呼ばず、QThread 上のワーカー（ui/async_workers.py）
#   が import_file()/process(...) を呼び出す。
# - ワーカーからは progress_cb/cancel_cb を受け取り、
#     * progress_cb(n): 進捗を通知（UIのプログレスバー更新用）
#     * cancel_cb() -> bool: ユーザーがキャンセルしたら True を返す
#   という“非同期フック”で UI と連携する。
# - 行単位の軽微エラーは self.warnings に蓄積（最後にワーカーがログ化）。
# - CSV自体が壊れている等の致命的エラーは RuntimeError を raise（ワーカー側で
#   『続行/中止』ダイアログに接続される）。

import csv
import unicodedata
import logging
from typing import Optional, Callable, Tuple, List

from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection
from mt_signal_search.repositories.base import SignalRepository

# progress/cancel は UI 非依存の関数参照を受け取る。
#   progress_cb: 処理の進み具合（読み込んだ行数など）を UI に伝えるためのコールバック
#   cancel_cb  : ユーザーがキャンセルを押したかどうかをワーカー経由で確認する関数
ProgressCB = Optional[Callable[[int], None]] #csv読み込み中に今何行まで処理をしたかを表示するためのやつ
CancelCB = Optional[Callable[[], bool]] #csv読み込みのループ中にキャンセルボタンが押されたかかをチェックするやつ

# 文字列正規化ユーティリティ
# - _norm     : NFKC（全角→半角など）+ 前後空白除去
# - _norm_id  : ID系（信号ID/BOX番号など）はさらに大文字化
# - _norm_expr: 論理式の記号ゆれ（∨/Ｖ/V, ＾, ＋, ー/−/–/―/- 等）を統一
def _norm(s: Optional[str]) -> str:
    """全角→半角・前後空白除去を行う（取り込みデータ）"""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", s).strip()

def _norm_id(s: Optional[str]) -> str:
    """ID系は NFKC + upper まで行う"""
    return _norm(s).upper()

def _norm_expr(s: Optional[str]) -> str:
    """論理式の表記ゆれを正規化（NFKC → 演算子統一 → 余分空白圧縮）"""
    t = _norm(s)
    # 論理演算子のゆれ
    t = (t.replace("∨", "v").replace("Ｖ", "v").replace("V", "v"))
    # XOR/AND など帽子記号のゆれ
    t = t.replace("＾", "^")
    # ダッシュ類はエムダッシュに統一
    t = (t.replace("−", "—").replace("–", "—").replace("―", "—")
           .replace("ー", "—").replace("-", "—"))
    # プラスのゆれ
    t = t.replace("＋", "+")
    # 余分な空白を1つに
    t = " ".join(t.split())
    return t

# 経由BOX列のパース
# CSVでは "BOX1,BOX2" のようなカンマ区切りで届く想定。
# - 空なら空タプル
# - 値ごとに _norm を通し、空要素は捨てる
def _parse_via_boxes(value: str) -> Tuple[str, ...]:
    if not value:
        return tuple()
    parts = [_norm(p) for p in value.split(",")]
    return tuple([p for p in parts if p])

class CSVSignalImporter:
    """signals.csv を読み込んで signals / logic_equations に投入する。

期待する列（テンプレ）：
  signal_id, signal_type, description, from_box, via_boxes,
  to_box, program_address, logic_group, logic_expr

設計ポリシー：
- logic_expr は必須（空はスキップし warnings に残す）
- 軽微エラーは self.warnings に蓄積、致命的エラーは RuntimeError にして上位へ
- 正規化（NFKC/大文字化/演算子ゆれ吸収）を通して DB/検索の揺れを抑える
"""
    def __init__(self, repo: SignalRepository):
        self.repo = repo
        # 行単位の軽微エラーを蓄積して、最後にワーカーがログ化するためのバッファ
        self.warnings: List[str] = []
        self._log = logging.getLogger("mt_signal.importer.csv")

    def import_file(self, path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) -> int:
        # 手順:
        #  1) CSV を開く（BOM付UTF-8 も許容）
        #  2) ヘッダ検証（テンプレ列がすべて存在するか）
        #  3) 各行をループ
        #     - cancel_cb() で中断可
        #     - 各列を正規化（ID系は大文字化 / 論理式は演算子ゆれ統一）
        #     - 必須チェック（signal_id / logic_expr）
        #     - SignalInfo を作って add_signal（UPSERT）
        #     - add_logic_equation で式を保存（出所はCSVファイルパス）
        #     - 進捗通知（任意の刻み）
        #  4) 致命的エラーは except 節で RuntimeError に変換し上位へ
        #  5) 終了時に最終進捗を通知
        count = 0
        self.warnings.clear()
        self._log.info("CSVSignalImporter start: %s", path)
        # --- ファイルオープン & ヘッダ検証（ここで失敗したら致命的エラーとして上げる）
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)  # 辞書形式でCSVデータを一行ずつ読み込む
                required = {"signal_id","signal_type","description","from_box","via_boxes","to_box","program_address","logic_group","logic_expr"}
                if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                    self._log.error("CSV header missing required columns. got=%s required=%s", reader.fieldnames, sorted(list(required)))
                    raise RuntimeError("CSV列名がテンプレートと一致しません。テンプレートを確認してください。")

                # --- 行ループ開始（ここからは1レコードずつ安全に処理し、軽微な問題は warnings へ）
                for i, row in enumerate(reader, 1):
                    # キャンセルが指示されたら安全に中断
                    if cancel_cb and cancel_cb():
                        self._log.info("CSV import canceled by user at row %d", i)
                        break  # キャンセルされたらループを抜ける

                    # 入力正規化：
                    #  - ID系（signal_id/from/to/addr）は NFKC + 大文字化
                    #  - via_boxes はカンマ区切りを分解し要素を正規化
                    #  - logic_expr は記号ゆれを吸収し空白を整える
                    sid = _norm_id(row.get("signal_id"))
                    type_row = _norm(row.get("signal_type"))
                    desc = _norm(row.get("description")) or "(CSV取り込み)"

                    if not sid:
                        self._log.warning("Row %d skipped: empty signal_id", i)
                        self.warnings.append(f"{i}行目: signal_id が空のためスキップ")
                        continue

                    from_box = _norm_id(row.get("from_box"))
                    via_boxes = _parse_via_boxes(_norm(row.get("via_boxes")))
                    # via の各要素も大文字に揃える
                    via_boxes = tuple(_norm_id(v) for v in via_boxes)
                    to_box = _norm_id(row.get("to_box"))
                    addr  = _norm_id(row.get("program_address") or sid)
                    grp = _norm(row.get("logic_group"))
                    expr = _norm_expr(row.get("logic_expr"))

                    # logic_expr は必須。空は登録しない（後でユーザーが把握できるよう warnings に記録）
                    if not expr:
                        self._log.warning("Row %d skipped: empty logic_expr (required)", i)
                        self.warnings.append(f"{i}行目: logic_expr が空（必須）")
                        continue

                    # signal_type の解釈：不明/不正は INTERNAL 扱い
                    try:
                        st_enum = SignalType(type_row.upper()) if type_row else SignalType.INTERNAL
                    except Exception:
                        st_enum = SignalType.INTERNAL

                    info = SignalInfo(
                        sid, st_enum, desc, from_box, via_boxes, to_box, addr, grp
                    )

                    # UPSERT想定：既存があれば置換する実装を許容
                    try:
                        self.repo.add_signal(info)
                    except Exception as e:
                        self._log.warning("Row %d add_signal failed: %s", i, e)
                        self.warnings.append(f"{i}行目: add_signal 失敗: {e}")
                        continue

                    # 条件式を保存。ソース（出所）として CSV のパスを残す
                    try:
                        try:
                            self.repo.add_logic_equation(sid, expr, source_label=path, source_page=None)
                        except TypeError:
                            self.repo.add_logic_equation(sid, expr, source_label=path)
                    except Exception as e:
                        self._log.warning("Row %d add_logic_equation failed: %s", i, e)
                        self.warnings.append(f"{i}行目: add_logic_equation 失敗: {e}")
                        continue

                    # 進捗通知（50行ごとなど適度な間隔）
                    count += 1
                    if progress_cb and i % 50 == 0:
                        progress_cb(i)
        # --- ここから致命的エラー（ファイルそのもの/エンコーディング/CSV構造）を RuntimeError に変換
        except FileNotFoundError:
            self._log.exception("CSV file not found: %s", path)
            raise RuntimeError(f"CSVファイルが見つかりません: {path}")
        except UnicodeDecodeError:
            self._log.exception("CSV decode error (expect UTF-8): %s", path)
            raise RuntimeError("CSVの文字コードをUTF-8にしてください（BOM付UTF-8推奨）")
        except csv.Error as e:
            self._log.exception("CSV parse error: %s", e)
            raise RuntimeError(f"CSV解析エラー: {e}")

        # 最終的な処理件数を通知
        if progress_cb:
            progress_cb(count)
        self._log.info("CSVSignalImporter done: imported=%d warnings=%d", count, len(self.warnings))
        return count


class CSVBoxConnImporter:
    """BOX間配線CSVの取り込み（テンプレ準拠）

期待する列（テンプレ）：
  from_box_name, from_box_no, kabel_no, to_box_no, to_box_name

設計ポリシー：
- 軽微エラーは self.warnings に蓄積、致命的エラーは RuntimeError で上位へ
- ID系（番号/ケーブルNo）は _norm_id で正規化、名称系は _norm
"""
    def __init__(self, repo: SignalRepository):
        self.repo = repo
        # 行単位の軽微エラーを蓄積して、最後にワーカーがログ化するためのバッファ
        self.warnings: List[str] = []
        self._log = logging.getLogger("mt_signal.importer.csv")

    def import_file(self, path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) -> int:
        # 手順:
        #  1) ファイルを開く & ヘッダ検証
        #  2) 各行をループしキャンセル可
        #  3) 正規化して add_box_connection に保存
        #  4) 保存失敗などの軽微エラーは warnings に残す
        #  5) 致命的エラーは except 節で RuntimeError にして上げる
        count = 0
        self.warnings.clear()
        self._log.info("CSVBoxConnImporter start: %s", path)
        # --- ファイルオープン & ヘッダ検証
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                # 必須列（テンプレに合わせる）
                required = {"from_box_name","from_box_no","kabel_no","to_box_no","to_box_name"}
                if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                    self._log.error("BOX CSV header missing required columns. got=%s required=%s", reader.fieldnames, sorted(list(required)))
                    raise RuntimeError("BOX配線CSVの列名がテンプレートと一致しません。")

                # --- 行ループ開始
                for i, row in enumerate(reader, 1):
                    # キャンセルが指示されたら安全に中断
                    if cancel_cb and cancel_cb():
                        self._log.info("BOX CSV import canceled by user at row %d", i)
                        break

                    # 入力正規化：番号系は _norm_id、名称系は _norm
                    from_box_name = _norm(row.get("from_box_name"))
                    from_box_no   = _norm_id(row.get("from_box_no"))
                    kabel_no      = _norm_id(row.get("kabel_no"))
                    to_box_no     = _norm_id(row.get("to_box_no"))
                    to_box_name   = _norm(row.get("to_box_name"))

                    # 主要列が全滅ならスキップ
                    if not any([from_box_name, from_box_no, kabel_no, to_box_no, to_box_name]):
                        self._log.warning("BOX row %d skipped: all major columns empty", i)
                        self.warnings.append(f"{i}行目: 主要列が空のためスキップ")
                        continue

                    # 実装差異に耐える二段構え（BoxConnection オブジェクト優先 / 引数バラ渡しにフォールバック）
                    try:
                        if BoxConnection is not None:
                            bc = BoxConnection(
                                from_box_name=from_box_name,
                                from_box_no=from_box_no,
                                kabel_no=kabel_no,
                                to_box_no=to_box_no,
                                to_box_name=to_box_name,
                            )
                            self.repo.add_box_connection(bc)
                        else:
                            raise TypeError
                    except Exception as e:
                        # 引数バラ渡しの実装にフォールバック or 失敗時は warnings
                        try:
                            self.repo.add_box_connection(from_box_name, from_box_no, kabel_no, to_box_no, to_box_name)
                        except Exception as e2:
                            self._log.warning("BOX row %d add_box_connection failed: %s", i, e or e2)
                            self.warnings.append(f"{i}行目: add_box_connection 失敗: {e or e2}")
                            continue

                    # 進捗通知（50行ごとなど適度な間隔）
                    count += 1
                    if progress_cb and i % 50 == 0:
                        progress_cb(i)
        # --- ここから致命的エラーを RuntimeError に変換
        except FileNotFoundError:
            self._log.exception("BOX CSV file not found: %s", path)
            raise RuntimeError(f"CSVファイルが見つかりません: {path}")
        except UnicodeDecodeError:
            self._log.exception("BOX CSV decode error (expect UTF-8): %s", path)
            raise RuntimeError("CSVの文字コードをUTF-8にしてください（BOM付UTF-8推奨）")
        except csv.Error as e:
            self._log.exception("BOX CSV parse error: %s", e)
            raise RuntimeError(f"CSV解析エラー: {e}")

        # 最終的な処理件数を通知
        if progress_cb:
            progress_cb(count)
        self._log.info("CSVBoxConnImporter done: imported=%d warnings=%d", count, len(self.warnings))
        return count