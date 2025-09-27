from typing import List, Dict, Optional, Callable
from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection

ProgressCB = Optional[Callable[[int], None]]
CancelCB = Optional[Callable[[], bool]]

def _norm_line(s: str) -> str: # NFKCで半角全角を統一して、前後の空白を除去
    import unicodedata
    return unicodedata.normalize("NFKC", s or ""). strip()

def _normalize_id(s: str) -> str: #idは大文字に合わせる
    return _norm_line(s).upper()

def _norm_ops(s: str) -> str:  # 演算子と記号の揺れを統一
    t = _norm_line(s)
    # 論理演算子のゆれ
    t = (t.replace('∨', 'v')
           .replace('Ｖ', 'v')
           .replace('V', 'v'))
    # XOR/AND 記号のゆれ
    t = (t.replace('＾', '^')
           .replace('^', '^'))
    # ダッシュ/マイナスのゆれをエムダッシュに統一
    t = (t.replace('−', '—')   # minus sign
           .replace('–', '—')  # en dash
           .replace('―', '—')  # horizontal bar
           .replace('ー', '—')  # katakana long sound
           .replace('-', '—')   # hyphen-minus
           .replace('➖', '—'))  # heavy minus sign
    # プラスのゆれ
    t = t.replace('＋', '+')
    # 余分な空白を1つに圧縮
    t = ' '.join(t.split())
    return t

def _paren_delta(s: str) -> int: #括弧の開閉バランスを計算するやつらしい
    delta = 0
    for ch in s:
        if ch in ('(', '（'):
            delta += 1
        elif ch in (')', '）'):
            delta -= 1
    return delta

class PDFProcessor:
    def process(self, file_path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) :
        raise NotImplementedError

class SimplePDFProcessor(PDFProcessor):
    """
    信号PDFの簡易パーサ（式抽出のみ重視）
    - パターン1:  Q3B0 = 04E ^ 351 ^ ...
    - パターン2:  見出し「Q3B0 説明」の次行以降が式
    ※ from_box / via_boxes / to_box は PDFからは取れないので空で返す
    """
    def __init__(self):
        self.logic_blocks: Dict[str, str] = {}
        self.warnings: List[str] = []

    def process(self, file_path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None) -> List[SignalInfo]: 
        #UI側に処理がどこまで終わったか、ユーザーがキャンセルボタンを押したか知らせる
        try:
            from pdf2image import convert_from_path 
            import pytesseract, re
        except Exception:
            raise RuntimeError('OCRモジュール未導入です。"pip install pdf2image pillow pytesseract" と Tesseract を導入してください。') # クリティカルなエラー表示

        pages = convert_from_path(file_path, dpi=300)
        texts = []
        for i, pg in enumerate(pages): # ページごとにOCR実行、キャンセル・進捗チェック
            if cancel_cb and cancel_cb(): # キャンセルをチェック
                break
            texts.append(pytesseract.image_to_string(pg,lang='jpn+eng'))
            if progress_cb: # 進捗をUI側に知らせる。　これでプログレスバーを更新するデータ
                progress_cb(i+1)
        
        text = _norm_ops("\n".join(texts))
        lines = [_norm_line(l) for l in text.splitlines()]

        import re
        eq_re    = re.compile(r'^\s*([A-Za-z]{1,3})\s*([0-9A-Za-z]+)\s*=\s*(.+)$')
        qhead_re = re.compile(r'^\s*(Q[0-9A-Za-z]+)\s*[:：\-–—]*\s*(.+)$')
        expr_re  = re.compile(r'^[0-9A-Za-z()（）_＿v^!＋+—\-\s]+$')

        signals: List[SignalInfo] = []
        seen = set()
        current_q: Optional[str] = None
        current_desc = ""
        buf: List[str] = []
        paren_balance = 0

        def flush():
            nonlocal buf, paren_balance
            if current_q and buf:
                expr = _norm_ops(" ".join(x.strip() for x in buf if x.strip()))
                if expr:
                    if paren_balance != 0:
                        #括弧不一致で警告としてログを蓄積（軽微なもの）
                        self.warnings.append(f"{current_q}: 括弧がうまく読み取れていない可能性: '{expr[:60]}...'")
                    self.logic_blocks[current_q] = expr
            buf = []
            paren_balance = 0

        for raw in lines:
            if not raw.strip(): 
                if current_q and paren_balance > 0:
                    #何も文字がない行に遭遇した時や式途中の空白に遭遇した時にスキップする
                    continue
                flush(); current_q=None; current_desc=""; continue #ここで確定してコンテキストをリセット
            
            m1 = eq_re.match(raw) #正しい形式でかつ論理式が一行で終わっているパターンの処理　　例: Q101 = 04E ^ 351 ^ 383
            if m1:
                flush() 
                sid = _normalize_id(f"{m1.group(1)}{m1.group(2)}") #　ID正規化
                rhs = _norm_ops (m1.group(3).strip()) #論理式正規化
                if sid not in seen:
                    signals.append(SignalInfo(sid, SignalType.OUTPUT, "(OCR取り込み)", "", tuple(), "", sid, ""))
                    seen.add(sid)
                self.logic_blocks[sid] = rhs
                current_q = None #コンテキストリセット
                continue
            
            m2 = qhead_re.match(raw) #見出しの次に式がある場合　、指揮ブロックを読み込んでいく。例: Q101 右内タンピングユニット下降 や Q101：右内 ... Q101-右内 ...
            if m2:
                flush()
                current_q = _normalize_id(m2.group(1))
                current_desc = _norm_line (m2.group(2))
                if current_q not in seen:
                    signals.append(SignalInfo(current_q, SignalType.OUTPUT, current_desc or "(OCR取り込み)", "", tuple(), "", current_q, ""))
                    seen.add(current_q)
                continue
            
            if current_q and expr_re.match(raw):  #見出しが出た後に論理式だけで構成された行が来たらバッファに貯める
                buf.append(raw.strip())
                paren_balance += _paren_delta(raw) #paren_balance == 0 になったところが式の“論理的な”切れ目の目安。
                continue
            
            if current_q: # 既に「この ID の式を読んでいます（current_q がある）」状態で、式っぽくない行が来たときの処理。
                if paren_balance > 0:
                    #括弧が閉じていない場合は継続しているとみなして取り込む
                    buf.append(raw.strip())
                    paren_balance += _paren_delta(raw)
                    continue
                else:
                    #一旦確定
                    flush(); current_q=None; current_desc=""
                    #この行を再評価して書式があっているか確認する
                    m1 = eq_re.match(raw)
                    if m1:
                        sid = _normalize_id(f"{m1.group(1)}{m1.group(2)}")
                        rhs = _norm_ops(m1.group(3).strip())
                        if sid not in seen:
                            signals.append(SignalInfo(sid, SignalType.OUTPUT, "(OCR取り込み)", "", tuple(),
                            "", sid, ""))
                            seen.add(sid)
                        self.logic_blocks[sid] = rhs
                        continue
                    m2 = qhead_re.match(raw)
                    if m2:
                        current_q = _normalize_id(m2.group(1))
                        current_desc = _norm_line(m2.group(2))
                        if current_q not in seen:
                            signals.append(SignalInfo(current_q, SignalType.OUTPUT, current_desc or "(OCR取り込み)", "", tuple(),
                            "", current_q, ""))
                            seen.add(current_q)
                         #OCRが誤認識した変な文字や、記号、ページ番号があれば無視する
                        continue

        flush()
        return signals #返り値は抽出できたSignal Infoのリスト　式はself.logic_blocks[sid]に格納

class BoxPDFProcessor(PDFProcessor):
    """BOX間配線一覧の簡易パーサ（表OCR）"""
    def process(self, file_path: str, progress_cb: ProgressCB = None, cancel_cb: CancelCB = None):
        try:
            from pdf2image import convert_from_path
            import pytesseract, re
        except Exception:
            raise RuntimeError('OCRモジュール未導入です。"pip install pdf2image pillow pytesseract" と Tesseract を導入してください。')

        pages = convert_from_path(file_path, dpi=300)
        texts = []
        for i, pg in enumerate(pages):
            if cancel_cb and cancel_cb():
                break
            texts.append(pytesseract.image_to_string(pg, lang='jpn+eng'))
            if progress_cb:
                progress_cb(i+1)
        text = "\n".join(texts)

        import re
        line_re = re.compile(
            r'^(?P<n1>\S.+?)\s+(?P<b1>[A-Za-z0-9\.]+)\s+(?P<kab>[A-Za-z0-9\.]+)\s+(?P<b2>[A-Za-z0-9\.]+)\s+(?P<n2>.+)$',
            re.M
        )
        conns = []
        for m in line_re.finditer(text):
            n1 = _norm_line(m.group('n1'))
            b1 = _normalize_id(m.group('b1'))
            kab = _normalize_id(m.group('kab'))
            b2 = _normalize_id(m.group('b2'))
            n2 = _norm_line(m.group('n2'))
            if len(n1) < 2 or len(n2) < 2:
                continue
            if any(h in n1 for h in ['Box名称','KABEL','KABELNo','見出し']):
                continue
            conns.append(BoxConnection(n1, b1, kab, b2, n2))
        return conns