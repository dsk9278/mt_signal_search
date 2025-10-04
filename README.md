入出力プログラム検索アプリ

このアプリは、MTTの制御プログラムを対象に、信号の入出力条件や配線経路を検索・編集・可視化するためのデスクトップアプリケーションです。

- **開発環境**: Python 3.11, PyQt5, SQLite  
- **主要機能**: 信号検索 / 編集 / PDF・CSVインポート / JSONエクスポート / お気に入り登録  

機能

•	信号検索
•	信号IDを入力して、条件式・入出力BOX・プログラムアドレスなどを検索
•	条件式をテーブル形式で確認
•	編集/追加
•	ギアボタン → 編集 から専用ダイアログを開き、信号の全項目を編集または新規追加可能
•	項目: 信号ID, 種別(INPUT/OUTPUT/INTERNAL), 説明, From, Via, To, アドレス, ロジックグループ, 条件式
•.  保存すると即座にDBへ反映 & 検索結果を自動更新
•	インポート
•	PDF から信号定義や BOX 間配線を抽出
•	CSV から信号一覧・BOX配線を一括インポート
•	エクスポート
•	信号データや BOX 配線のテンプレートCSVを出力
•	任意のデータをJSON形式でエクスポート
•	お気に入り
•	よく使う信号をお気に入りに登録し、メニューから一覧確認可能
画面構成

•	検索画面: 入力欄＋結果テーブル
•	ロジック表示パネル: 選択した信号の条件式をカード形式で表示
•	ギアメニュー: 編集 / 保存 / お気に入り の3ボタン（左上に配置）
•	編集ダイアログ: 全項目を入力可能。新規追加/編集両対応。

ディレクトリ構成（抜粋）

mt_signal_search/
├── app.py
├── main.py
├── __main__.py
├── README.md
├── requirements.txt
├── .gitignore
├── domain/
│   └── models.py ほか
├── io_importers/
│   ├── csv_importers.py
│   └── pdf_importers.py
├── repositories/
│   ├── base.py
│   ├── sqlite_impl.py
│   └── favorites_json.py
├── services/
│   └── services.py
└── ui/
    ├── main_window.py
    ├── components/
    │   ├── search_component.py
    │   ├── logic_display.py
    │   ├── floating_menu.py
    │   └── gear_button.py
    └── dialogs/
        └── edit_signal_dialog.py

CSVテンプレート例

信号テンプレート
signal_id,signal_type,description,from_box,via_boxes,to_box,program_address,logic_group,logic_expr
Q3B0,OUTPUT,右内タンピングユニット下降,BOX3,"BOX5,BOX6",BOX7,Q3B0,ロジック2,"04E^351^383^3BD^((065^354)v038)"

非同期インポートの仕組み（UI ↔ Worker ↔ Importer ↔ Repository）

本アプリでは、CSV/PDF の取り込みを **別スレッド（QThread）**で実行し、UIフリーズを防ぎます。
処理は下図のように流れます。

[UI(MainWindow)]
   └─(QThread起動)→ [Worker (ui/async_workers.py)]
        └─ import_file()/process() 呼び出し → [Importer (io_importers/*.py)]
             └─ DB保存 → [Repository (repositories/sqlite_impl.py)]


接続点（重要な関数）
	•	Worker → Importer の入口
	•	CSV: CSVSignalImporter.import_file(path, progress_cb, cancel_cb)
	•	CSV(配線): CSVBoxConnImporter.import_file(path, progress_cb, cancel_cb)
	•	PDF: SimplePDFProcessor.process(path, progress_cb, cancel_cb)
	•	Importer → Worker の連携
	•	progress_cb(n) … Workerの progress シグナルへ（UIのプログレスバー更新）
	•	cancel_cb() -> bool … UIのキャンセル操作を検知して安全に中断
	•	軽微エラー … importer.warnings （Workerがログ化して UI へ報告）
	•	致命的エラー … RuntimeError を raise（Worker が _confirm() で 続行/中止 をUIに確認）

Worker が発行するシグナル（ui/async_workers.py）
	•	started() …… 取り込み開始
	•	progress(int) …… 進捗通知（行数/ページ数）
	•	ask_confirm(str) …… 致命的エラー時に Yes/No 確認（UIは回答後 set_user_decision(True/False) を呼ぶ）
	•	report(summary: str, log_path: str) …… 軽微エラーの集計結果とログファイルの場所
	•	finished(...) …… 正常終了（CSV: 件数 / PDF: (signals, box_conns)）
	•	error(str) …… 例外（traceback）
	•	canceled() …… キャンセル終了

典型フロー

1) 正常系（CSVの例）
	1.	UIが ImportCSVWorker を QThread にのせて run() を開始
	2.	Worker が CSVSignalImporter.import_file(..., progress_cb, cancel_cb) をコール
	3.	Importer が各行を処理し、適宜 progress_cb(n) を呼ぶ
	4.	Importer が repo.add_signal() / repo.add_logic_equation() で DB 保存
	5.	軽微エラーは importer.warnings に貯める
	6.	Worker が warnings をログ化 → report(summary, log_path)
	7.	Worker が finished(count) を emit → UIが再検索などを実行

2) キャンセル
	•	UIの Cancel → worker.cancel()
	•	Importer のループ内で cancel_cb() が True を返し、中断
	•	Worker が canceled() を emit

3) 致命的エラー（例：CSV列壊れ/文字コード不正）
	•	Importer が RuntimeError を raise
	•	Worker が ask_confirm(msg) → UIで「続行/中止」を表示
	•	Yes: エラーをスキップして続行（内容はログへ）
	•	No: error(traceback) を emit して終了

UI 実装の最小例（抜粋）

# Worker 起動
self.thread = QThread(self)
self.worker = ImportCSVWorker(db_path=self.db_path, csv_path=path, mode="signals")
self.worker.moveToThread(self.thread)
self.thread.started.connect(self.worker.run)

# シグナル接続
self.worker.progress.connect(self._on_progress)
self.worker.report.connect(self._on_report)
self.worker.finished.connect(self._on_finished)
self.worker.canceled.connect(self._on_canceled)
self.worker.error.connect(self._on_error)
self.worker.ask_confirm.connect(self._on_worker_confirm)  # Yes/No

self.thread.start()

# Yes/No の回答返却
def _on_worker_confirm(self, message: str):
    res = QMessageBox.question(self, "確認", message,
                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    self.worker.set_user_decision(res == QMessageBox.Yes)


Importer 側の約束事（要点）
	•	progress_cb/cancel_cb を必ず受け取れるシグネチャにする
	•	軽微エラーは self.warnings に蓄積（例：必須列欠落の行）
	•	致命的エラーは RuntimeError を raise（Worker が UI に確認）
	•	正規化は統一（NFKC、ID大文字化、演算子ゆれ：∨/Ｖ/V→v, ＾→^, ＋→+, —統一、空白圧縮）

トラブルシュート
	•	プログレスが動かない
→ Importer 内で progress_cb(n) を呼んでいるか確認（刻みは任意）
	•	キャンセルが効かない
→ ループ内で if cancel_cb and cancel_cb(): break を入れているか
	•	ログが出ない
→ Importer に self.warnings が実装されているか／Worker が report() を受けているか
	•	UIが固まる
→ Import をメインスレッドで呼んでいないか（必ず QThread + Worker で）

今後の拡張予定

•	条件式の数式レンダリング（!501 → 上棒表記）
•	Webアプリ化（StreamlitやFastAPI経由）
•	ロジック間のグラフ可視化
•	ユーザー権限追加

ライセンス

このアプリは個人学習・業務効率化のために開発しています。

base.pyとsqlite_impl.pyを分けた理由（9.26）
1.	疎結合
	•	CSV Importer や UI は「repo.add_signal(signal)」としか書かない。
	•	SQLite 以外の実装（例：PostgreSQL版、メモリDB版）に差し替えても、呼び出しコードは一切変えなくてよい。
	2.	テストしやすい
	•	テスト用に「SQLiteじゃなくてInMemoryRepository」を用意して差し替えるだけでユニットテスト可能。
	3.	役割がはっきり分かれる
	•	base = できること一覧（契約）
	•	sqlite_impl = 実際の処理（契約を守る中身）