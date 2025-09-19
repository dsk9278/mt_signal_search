import sqlite3, json
from typing import List, Optional
from mt_signal_search.domain.models import SignalInfo, SignalType, BoxConnection
from mt_signal_search.repositories.base import SignalRepository

class SQLiteSignalRepository(SignalRepository):
    def __init__(self, db_path: str = "signal_database.db"):
        self.db_path = db_path
        self._init_database()
        self._insert_sample_data()

    def _init_database(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY,
                    signal_id TEXT UNIQUE,
                    signal_type TEXT,
                    description TEXT,
                    from_box TEXT,
                    via_boxes TEXT,
                    to_box TEXT,
                    program_address TEXT,
                    logic_group TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS logic_equations (
                    id INTEGER PRIMARY KEY,
                    target_signal_id TEXT UNIQUE,
                    raw_expr TEXT,
                    normalized_expr TEXT,
                    source_label TEXT,
                    source_page INTEGER,
                    last_imported_at TEXT,
                    FOREIGN KEY(target_signal_id) REFERENCES signals(signal_id)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS box_connections (
                    id INTEGER PRIMARY KEY,
                    from_box_name TEXT,
                    from_box_no TEXT,
                    kabel_no TEXT,
                    to_box_no TEXT,
                    to_box_name TEXT
                )
            ''')
            conn.commit()

    def _row_to_signal(self, row: tuple) -> SignalInfo:
        via = tuple(json.loads(row[5] or "[]"))
        return SignalInfo(
            signal_id=row[1],
            signal_type=SignalType(row[2]),
            description=row[3],
            from_box=row[4] or "",
            via_boxes=via,
            to_box=row[6] or "",
            program_address=row[7] or "",
            logic_group=row[8] if len(row) > 8 else ""
        )

    def _insert_sample_data(self) -> None:
        samples = [
            SignalInfo("X01", SignalType.INPUT,  "近接スイッチ1", "BOX1", tuple(), "BOX7", "X01", "ロジック1"),
            SignalInfo("X02", SignalType.INPUT,  "近接スイッチ2", "BOX1", ("BOX5",), "BOX7", "X02", "ロジック1"),
            SignalInfo("Q124",SignalType.OUTPUT, "制御出力",       "BOX3", ("BOX5","BOX6"), "BOX7", "Q124", "ロジック2"),
        ]
        for s in samples:
            try:
                self.add_signal(s)
            except Exception:
                pass

    # --- SignalRepository impl ---
    def add_signal(self, signal: SignalInfo) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO signals
                (signal_id, signal_type, description, from_box, via_boxes, to_box, program_address, logic_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(signal_id) DO UPDATE SET
                    signal_type=excluded.signal_type,
                    description=excluded.description,
                    from_box=excluded.from_box,
                    via_boxes=excluded.via_boxes,
                    to_box=excluded.to_box,
                    program_address=excluded.program_address,
                    logic_group=excluded.logic_group
            ''', (
                signal.signal_id,
                signal.signal_type.value,
                signal.description,
                signal.from_box,
                json.dumps(list(signal.via_boxes), ensure_ascii=False),
                signal.to_box,
                signal.program_address,
                signal.logic_group
            ))
            conn.commit()

    def get_signal(self, signal_id: str) -> Optional[SignalInfo]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM signals WHERE signal_id = ?', (signal_id,))
            row = c.fetchone()
            return self._row_to_signal(row) if row else None

    def search_signals(self, keyword: str) -> List[SignalInfo]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            like = f"%{keyword}%"
            c.execute('''
                SELECT * FROM signals 
                WHERE signal_id LIKE ? OR description LIKE ? OR program_address LIKE ? 
                   OR from_box LIKE ? OR to_box LIKE ?
            ''', (like, like, like, like, like))
            return [self._row_to_signal(r) for r in c.fetchall()]

    def get_signals_by_logic_group(self, logic_group: str) -> List[SignalInfo]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM signals WHERE logic_group = ?', (logic_group,))
            return [self._row_to_signal(r) for r in c.fetchall()]

    def get_all_logic_groups(self) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT DISTINCT logic_group FROM signals WHERE logic_group != ""')
            return [r[0] for r in c.fetchall()]

    def add_logic_equation(self, target_signal_id: str, raw_expr: str, source_label: str = "", source_page: int = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO logic_equations (target_signal_id, raw_expr, source_label, source_page, last_imported_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(target_signal_id) DO UPDATE SET
                raw_expr=excluded.raw_expr,
                source_label=excluded.source_label,
                source_page=excluded.source_page,
                last_imported_at=datetime('now')
            ''', (target_signal_id, raw_expr, source_label, source_page))
            conn.commit()

    def add_box_connection(self, conn_rec: BoxConnection) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO box_connections (from_box_name, from_box_no, kabel_no, to_box_no, to_box_name)
                VALUES (?, ?, ?, ?, ?)
            ''', (conn_rec.from_box_name, conn_rec.from_box_no, conn_rec.kabel_no, conn_rec.to_box_no, conn_rec.to_box_name))
            conn.commit()

    def get_logic_expr(self, target_signal_id: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT raw_expr FROM logic_equations WHERE target_signal_id =  ?', (target_signal_id,))
            row = c.fetchone()
            return row[0] if row and row[0] else None
        
    def get_source_label(self, target_signal_id: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT source_label FROM logic_equations WHERE target_signal_id = ?', (target_signal_id,))
            row = c.fetchone()
            return row[0] if row and row[0] else None       