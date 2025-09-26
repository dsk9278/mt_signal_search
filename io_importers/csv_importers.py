# -*- coding: utf-8 -*-
"""CSV importers for signals and box connections.

- CSVSignalImporter: テンプレ `signal_id, signal_type, ... , logic_expr` を読み込む
- CSVBoxConnImporter: テンプレ `from_box_name, ... , to_box_name` を読み込む

UI には依存しない純粋な I/O レイヤ。例外は上位で拾いやすいように必要最小限のみ捕捉。
`progress_cb` と `cancel_cb` はワーカー(QThread)側から渡せるよう任意引数にしている。
"""

import csv
import unicodedata
from typing import Optional, Callable, Tuple

from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection
from mt_signal_search.repositories.base import SignalRepository

ProgressCB = Optional[Callable[[int], None]] #csv読み込み中に今何行まで処理をしたかを表示するためのやつ
CancelCB = Optional[Callable[[], bool]] #csv読み込みのループ中にキャンセルボタンが押されたかかをチェックするやつ

def _norm(s: Optional[str]) -> str:
    """全角→半角・前後空白除去を行う（取り込みデータ）"""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", s).strip()

def _parse_via_boxes(value: str) -> Tuple[str, ...]:
    if not value:
        return tuple()
    parts = [_norm(p) for p in value.split(",")]
    return tuple([p for p in parts if p])

class CSVSignalImporter:
    """signals.csv を読み込んで signals / logic_equations に投入（logic_expr 必須）"""
    def __init__(self, repo: SignalRepository):
        self.repo = repo

    def import_file(self, path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) -> int:
        count = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f) #辞書形式でCSVデータを一行ずつ読み込む
            for i, row in enumerate(reader, 1): 
                if cancel_cb and cancel_cb():
                    break #キャンセルボタンが押されたらループを抜ける

                sid = _norm(row.get("signal_id"))
                type_row = _norm(row.get("signal_type"))
                desc = _norm(row.get("description")) or "(CSV取り込み)"
                if not sid:
                    # signal_idは必須
                    continue
                from_box =_norm(row.get("from_box"))
                via_boxes = _parse_via_boxes(_norm(row.get("via_boxes")))
                to_box = _norm(row.get("to_box"))
                addr  = _norm(row.get("program_address")or sid)
                grp = _norm(row.get("logic_group"))
                expr = _norm(row.get("logic_expr"))
                
                #exprは必須
                if not (expr):  #  exprは必須。exprがない場合はスキップ
                    continue

                # signal_type_row の解決（不明/表記ゆれは INTERNAL）
                try:
                    st_enum = SignalType(type_row.upper()) if type_row else SignalType.INTERNAL
                except Exception:
                    st_enum = SignalType.INTERNAL

                info = SignalInfo(
                    sid, st_enum, desc, from_box, via_boxes, to_box, addr, grp
                )

                # UPSERT 想定
                self.repo.add_signal(info)

                # 条件式を保存（source_label は実ファイルパス）
                # リポジトリ実装差異に配慮（source_page あり/なし）
                try:
                    self.repo.add_logic_equation(sid, expr, source_label=path, source_page=None)
                except TypeError:
                    self.repo.add_logic_equation(sid, expr, source_label=path)

                count += 1
                if progress_cb and i % 50 == 0:
                    progress_cb(i)
        return count


class CSVBoxConnImporter:
    """BOX間配線CSVの取り込み（テンプレ準拠）"""

    def __init__(self, repo: SignalRepository):
        self.repo = repo

    def import_file(self, path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) -> int:
        count = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 1):
                if cancel_cb and cancel_cb():
                    break

                from_box_name = _norm(row.get("from_box_name"))
                from_box_no   = _norm(row.get("from_box_no"))
                kabel_no      = _norm(row.get("kabel_no"))
                to_box_no     = _norm(row.get("to_box_no"))
                to_box_name   = _norm(row.get("to_box_name"))

                # 主要列が全滅ならスキップ
                if not any([from_box_name, from_box_no, kabel_no, to_box_no, to_box_name]):
                    continue

                # リポジトリの署名差異に耐える二段構え
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
                except Exception:
                    # 引数バラ渡しの実装にフォールバック
                    try:
                        self.repo.add_box_connection(from_box_name, from_box_no, kabel_no, to_box_no, to_box_name)
                    except Exception:
                        # 実装無し・失敗はスキップ（行単位で止めない）
                        pass

                count += 1
                if progress_cb and i % 50 == 0:
                    progress_cb(i)
        return count