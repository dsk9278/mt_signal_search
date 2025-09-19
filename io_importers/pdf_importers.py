from typing import List, Dict, Optional
from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection

class PDFProcessor:
    def process(self, file_path: str): raise NotImplementedError

class SimplePDFProcessor(PDFProcessor):
    """
    信号PDFの簡易パーサ（式抽出のみ重視）
    - パターン1:  Q3B0 = 04E ^ 351 ^ ...
    - パターン2:  見出し「Q3B0 説明」の次行以降が式
    ※ from_box / via_boxes / to_box は PDFからは取れないので空で返す
    """
    def __init__(self):
        self.logic_blocks: Dict[str, str] = {}

    def process(self, file_path: str) -> List[SignalInfo]:
        try:
            from pdf2image import convert_from_path
            import pytesseract, re
        except Exception:
            raise RuntimeError('OCRモジュール未導入です。"pip install pdf2image pillow pytesseract" と Tesseract を導入してください。')

        def normalize_ops(s: str) -> str:
            return (s.replace('∨','v').replace('Ｖ','v')
                    .replace('＾','^').replace('ー','—')
                    .replace('−','—').replace('-', '—')
                    .replace('　',' ').replace('\t',' '))

        pages = convert_from_path(file_path, dpi=300)
        texts = [pytesseract.image_to_string(pg, lang='jpn+eng') for pg in pages]
        text = normalize_ops("\n".join(texts))
        lines = [l.rstrip() for l in text.splitlines()]

        import re
        eq_re    = re.compile(r'^\s*([A-Za-z]{1,3})\s*([0-9A-Za-z]+)\s*=\s*(.+)$')
        qhead_re = re.compile(r'^\s*(Q[0-9A-Za-z]+)\s+(.+)$')
        expr_re  = re.compile(r'^[0-9A-Za-z()（）_＿vV^—\-\s]+$')

        signals: List[SignalInfo] = []
        seen = set()
        current_q: Optional[str] = None
        current_desc = ""
        buf: List[str] = []

        def flush():
            if current_q and buf:
                expr = " ".join(x.strip() for x in buf if x.strip())
                if expr:
                    self.logic_blocks[current_q] = expr

        for raw in lines:
            if not raw.strip():
                flush(); current_q=None; current_desc=""; buf=[]; continue
            m1 = eq_re.match(raw)
            if m1:
                sid = f"{m1.group(1).upper()}{m1.group(2)}"
                rhs = m1.group(3).strip()
                if sid not in seen:
                    signals.append(SignalInfo(sid, SignalType.OUTPUT, "(OCR取り込み)", "", tuple(), "", sid, ""))
                    seen.add(sid)
                self.logic_blocks[sid] = rhs
                flush(); current_q=None; buf=[]; continue
            m2 = qhead_re.match(raw)
            if m2:
                flush()
                current_q = m2.group(1).strip()
                current_desc = m2.group(2).strip()
                if current_q not in seen:
                    signals.append(SignalInfo(current_q, SignalType.OUTPUT, current_desc or "(OCR取り込み)", "", tuple(), "", current_q, ""))
                    seen.add(current_q)
                buf=[]; continue
            if current_q and expr_re.match(raw):
                buf.append(raw.strip())

        flush()
        return signals

class BoxPDFProcessor(PDFProcessor):
    """BOX間配線一覧の簡易パーサ（表OCR）"""
    def process(self, file_path: str):
        try:
            from pdf2image import convert_from_path
            import pytesseract, re
        except Exception:
            raise RuntimeError('OCRモジュール未導入です。"pip install pdf2image pillow pytesseract" と Tesseract を導入してください。')

        pages = convert_from_path(file_path, dpi=300)
        texts = [pytesseract.image_to_string(pg, lang='jpn+eng') for pg in pages]
        text = "\n".join(texts)

        import re
        line_re = re.compile(
            r'^(?P<n1>\S.+?)\s+(?P<b1>[A-Za-z0-9\.]+)\s+(?P<kab>[A-Za-z0-9\.]+)\s+(?P<b2>[A-Za-z0-9\.]+)\s+(?P<n2>.+)$',
            re.M
        )
        conns = []
        for m in line_re.finditer(text):
            n1 = m.group('n1').strip()
            b1 = m.group('b1').strip()
            kab = m.group('kab').strip()
            b2 = m.group('b2').strip()
            n2 = m.group('n2').strip()
            if len(n1) < 2 or len(n2) < 2:
                continue
            if any(h in n1 for h in ['Box名称','KABEL','KABELNo','見出し']):
                continue
            conns.append(BoxConnection(n1, b1, kab, b2, n2))
        return conns