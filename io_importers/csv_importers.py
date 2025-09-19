import csv
from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection
from mt_signal_search.repositories.sqlite_impl import SQLiteSignalRepository

class CSVSignalImporter:
    """signals.csv を読み込んで signals / logic_equations に投入（logic_expr 必須）"""
    def __init__(self, repo: SQLiteSignalRepository):
        self.repo = repo

    def import_file(self, path: str) -> int:
        count = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sid = (r.get("signal_id") or "").strip()
                st  = (r.get("signal_type") or "INTERNAL").strip().upper()
                desc= (r.get("description") or "").strip() or "(CSV取り込み)"
                from_box = (r.get("from_box") or "").strip()
                via_raw  = (r.get("via_boxes") or "").strip()
                to_box   = (r.get("to_box") or "").strip()
                addr     = (r.get("program_address") or sid).strip()
                grp      = (r.get("logic_group") or "").strip()
                expr     = (r.get("logic_expr") or "").strip()

                if not (sid and expr):  # logic_exprは必須
                    continue

                via = tuple([x.strip() for x in via_raw.split(",") if x.strip()])
                # signal_typeの不正値はINTERNALにフォールバック
                try:
                    st_enum = SignalType(st)
                except Exception:
                    st_enum = SignalType.INTERNAL
                info = SignalInfo(
                    sid, st_enum, desc, from_box, via, to_box, addr, grp
                )
                try:
                    self.repo.add_signal(info)
                    self.repo.add_logic_equation(sid, expr, source_label="(csv)")
                    count += 1
                except Exception:
                    pass
        return count

class CSVBoxConnImporter:
    """box_connections.csv を読み込んで box_connections に投入"""
    def __init__(self, repo: SQLiteSignalRepository):
        self.repo = repo

    def import_file(self, path: str) -> int:
        count = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    bc = BoxConnection(
                        from_box_name=(r.get("from_box_name") or "").strip(),
                        from_box_no=(r.get("from_box_no") or "").strip(),
                        kabel_no=(r.get("kabel_no") or "").strip(),
                        to_box_no=(r.get("to_box_no") or "").strip(),
                        to_box_name=(r.get("to_box_name") or "").strip(),
                    )
                    if not (bc.from_box_name and bc.kabel_no and bc.to_box_name):
                        continue
                    self.repo.add_box_connection(bc)
                    count += 1
                except Exception:
                    pass
        return count