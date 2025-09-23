入出力プログラム検索アプリ

このアプリは、鉄道や産業機械などの制御プログラムを対象に、信号の入出力条件や配線経路を検索・編集・可視化するためのデスクトップアプリケーションです。
PyQt5 を用いた GUI と SQLite データベースを組み合わせて構築されています。

主な機能

•	信号検索
•	信号IDを入力して、条件式・入出力BOX・プログラムアドレスなどを検索
•	条件式をテーブル形式で確認
•	編集/追加
•	ギアボタン → 編集 から専用ダイアログを開き、信号の全項目を編集または新規追加可能
•	項目: 信号ID, 種別(INPUT/OUTPUT/INTERNAL), 説明, From, Via, To, アドレス, ロジックグループ, 条件式
•保存すると即座にDBへ反映 & 検索結果を自動更新
•	インポート
•	PDF から信号定義や BOX 間配線を抽出
•	CSV から信号一覧・BOX配線を一括インポート
•	エクスポート
•	信号データや BOX 配線のテンプレートCSVを出力
•	任意のデータをJSON形式でエクスポート
•	お気に入り
•	よく使う信号をお気に入りに登録し、メニューから一覧確認可能

🖥️ 画面構成
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


今後の拡張予定
•	条件式の数式レンダリング（!501 → 上棒表記）
•	Webアプリ化（StreamlitやFastAPI経由）
•	ロジック間のグラフ可視化
•	ユーザー権限追加

ライセンス

このアプリは個人学習・業務効率化のために開発しています。