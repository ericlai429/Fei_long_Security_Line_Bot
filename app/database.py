import json
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.email_helper import normalize_and_validate_email

DB_FILE = "data/storage.json"
_lock = threading.Lock()

class Database:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._load()

    def _load(self):
        with _lock:
            if not os.path.exists(self.db_path):
                self.data = {
                    "master_pin": settings.MASTER_PIN,
                    "roles": {
                        "admins": settings.admin_id_list or ["admin_super"],
                        "schedule_officers": [],
                        "managers": []
                    },
                    "groups": {
                        "test_sandbox": {
                            "group_id": "test_sandbox",
                            "group_name": "三總測試群",
                            "expected_group_name": "三總測試群",
                            "sheet_tab": "三總保全內部群",
                            "leader_email": "ericlai429@gmail.com",
                            "is_email_verified": True,
                            "verified_leader_user_id": "",
                            "pin_code": settings.DEFAULT_PIN,
                            "pin_updated_at": datetime.now().isoformat(),
                            "is_unlocked": False,
                            "unlocked_with_pin": ""
                        },
                        "tsgh_internal": {
                            "group_id": "tsgh_internal",
                            "group_name": "三總保全內部群",
                            "expected_group_name": "三總保全內部群",
                            "sheet_tab": "三總保全內部群",
                            "leader_email": "ericlai429@gmail.com",
                            "is_email_verified": True,
                            "verified_leader_user_id": "",
                            "pin_code": settings.DEFAULT_PIN,
                            "pin_updated_at": datetime.now().isoformat(),
                            "is_unlocked": False,
                            "unlocked_with_pin": ""
                        }
                    }
                }
                self._save_unsafe()
            else:
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
                    if "roles" not in self.data:
                        self.data["roles"] = {
                            "admins": settings.admin_id_list or ["admin_super"],
                            "schedule_officers": [],
                            "managers": []
                        }
                except Exception:
                    self.data = {
                        "master_pin": settings.MASTER_PIN,
                        "roles": {"admins": settings.admin_id_list, "schedule_officers": [], "managers": []},
                        "groups": {}
                    }

    def _save_unsafe(self):
        tmp_path = self.db_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.db_path)

    def save(self):
        with _lock:
            self._save_unsafe()

    # --- Role-Based Permission Check ---
    def is_authorized_manager(self, user_id: str) -> bool:
        if not user_id:
            return False
        if settings.DEBUG_MODE and user_id in ["test_user_chen", "admin_super"]:
            return True

        with _lock:
            roles = self.data.setdefault("roles", {})
            admins = set(settings.admin_id_list + roles.get("admins", []))
            officers = set(roles.get("schedule_officers", []))
            managers = set(roles.get("managers", []))
            return user_id in (admins | officers | managers)

    def get_role_name(self, user_id: str) -> str:
        with _lock:
            roles = self.data.get("roles", {})
            if user_id in settings.admin_id_list or user_id in roles.get("admins", []):
                return "Admin 系統管理員"
            if user_id in roles.get("schedule_officers", []):
                return "排班小姐"
            if user_id in roles.get("managers", []):
                return "保全經理"
    def add_authorized_role(self, user_id: str, role: str):
        with _lock:
            roles = self.data.setdefault("roles", {})
            key = "admins" if role == "admin" else ("schedule_officers" if role in ["officer", "排班小姐"] else "managers")
            if key not in roles:
                roles[key] = []
            if user_id not in roles[key]:
                roles[key].append(user_id)
            self._save_unsafe()

    def list_authorized_roles(self) -> Dict[str, List[str]]:
        with _lock:
            roles = self.data.setdefault("roles", {})
            return {
                "admins": list(set(settings.admin_id_list + roles.get("admins", []))),
                "schedule_officers": roles.get("schedule_officers", []),
                "managers": roles.get("managers", [])
            }

    def add_manager_role(self, user_id: str, role_type: str) -> bool:
        with _lock:
            roles = self.data.setdefault("roles", {})
            if role_type == "officer":
                officers = roles.setdefault("schedule_officers", [])
                if user_id not in officers:
                    if len(officers) >= 2:
                        officers.pop(0)
                    officers.append(user_id)
                    self._save_unsafe()
                    return True
            elif role_type == "manager":
                managers = roles.setdefault("managers", [])
                if user_id not in managers:
                    managers.append(user_id)
                    self._save_unsafe()
                    return True
            elif role_type == "admin":
                admins = roles.setdefault("admins", [])
                if user_id not in admins:
                    admins.append(user_id)
                    self._save_unsafe()
                    return True
        return False

    # --- Master PIN Operations ---
    def get_master_pin(self) -> str:
        with _lock:
            return self.data.get("master_pin", settings.MASTER_PIN)

    def set_master_pin(self, new_master_pin: str) -> bool:
        with _lock:
            self.data["master_pin"] = new_master_pin
            self._save_unsafe()
            return True

    # --- Group / Whitelist Operations ---
    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        with _lock:
            return self.data.get("groups", {}).get(group_id)

    def list_groups(self) -> List[Dict[str, Any]]:
        with _lock:
            return list(self.data.get("groups", {}).values())

    def upsert_group(
        self,
        group_id: str,
        group_name: Optional[str] = None,
        sheet_tab: Optional[str] = None,
        pin_code: Optional[str] = None,
        expected_group_name: Optional[str] = None,
        leader_email: Optional[str] = None
    ) -> Dict[str, Any]:
        with _lock:
            groups = self.data.setdefault("groups", {})
            group = groups.setdefault(group_id, {
                "group_id": group_id,
                "group_name": group_name or f"群組_{group_id[-6:]}",
                "expected_group_name": expected_group_name or group_name or f"群組_{group_id[-6:]}",
                "sheet_tab": sheet_tab or "三總保全內部群",
                "leader_email": "",
                "is_email_verified": False,
                "verified_leader_user_id": "",
                "pin_code": pin_code or settings.DEFAULT_PIN,
                "pin_updated_at": datetime.now().isoformat(),
                "is_unlocked": False,
                "unlocked_with_pin": ""
            })

            if group_name:
                group["group_name"] = group_name
            if expected_group_name:
                group["expected_group_name"] = expected_group_name
            elif group_name and not group.get("expected_group_name"):
                group["expected_group_name"] = group_name
            if sheet_tab:
                group["sheet_tab"] = sheet_tab
            if leader_email is not None:
                norm_email, _, _ = normalize_and_validate_email(leader_email)
                if norm_email != group.get("leader_email", ""):
                    group["leader_email"] = norm_email
                    group["is_email_verified"] = False
                    group["verified_leader_user_id"] = ""
            if pin_code and pin_code != group.get("pin_code"):
                group["pin_code"] = pin_code
                group["pin_updated_at"] = datetime.now().isoformat()
                group["is_unlocked"] = False
                group["unlocked_with_pin"] = ""

            self._save_unsafe()
            return group

    def set_leader_email(self, group_id: str, email: str) -> bool:
        norm_email, _, _ = normalize_and_validate_email(email)
        with _lock:
            group = self.data.setdefault("groups", {}).get(group_id)
            if group:
                group["leader_email"] = norm_email
                group["is_email_verified"] = False
                group["verified_leader_user_id"] = ""
                self._save_unsafe()
                return True
        return False

    def delete_leader_email(self, group_id: str) -> bool:
        with _lock:
            group = self.data.setdefault("groups", {}).get(group_id)
            if group:
                group["leader_email"] = ""
                group["is_email_verified"] = False
                group["verified_leader_user_id"] = ""
                self._save_unsafe()
                return True
        return False

    def verify_leader_email_and_pin(self, group_id: str, input_email: str, input_pin: str, user_id: str = "") -> bool:
        norm_input_email, _, _ = normalize_and_validate_email(input_email)
        with _lock:
            group = self.data.setdefault("groups", {}).get(group_id)
            if not group:
                return False

            expected_email = group.get("leader_email", "")
            expected_pin = str(group.get("pin_code", settings.DEFAULT_PIN)).strip()

            email_match = (not expected_email) or (norm_input_email == expected_email)
            pin_match = (input_pin.strip() == expected_pin)

            if email_match and pin_match:
                group["is_email_verified"] = True
                if user_id:
                    group["verified_leader_user_id"] = user_id
                group["is_unlocked"] = True
                group["unlocked_with_pin"] = input_pin.strip()
                self._save_unsafe()
                return True
            return False

    def delete_group(self, group_id: str) -> bool:
        with _lock:
            groups = self.data.setdefault("groups", {})
            if group_id in groups:
                del groups[group_id]
                self._save_unsafe()
                return True
            return False

    def set_expected_group_name(self, group_id: str, expected_name: str) -> bool:
        with _lock:
            group = self.data.setdefault("groups", {}).get(group_id)
            if group:
                group["expected_group_name"] = expected_name
                self._save_unsafe()
                return True
        return False

    def update_actual_group_name(self, group_id: str, actual_name: str) -> bool:
        with _lock:
            group = self.data.setdefault("groups", {}).get(group_id)
            if group:
                group["group_name"] = actual_name
                self._save_unsafe()
                return True
        return False

    def set_group_pin(self, group_id: str, new_pin: str) -> bool:
        if not (new_pin.isdigit() and 3 <= len(new_pin) <= 4):
            return False
        with _lock:
            group = self.data.setdefault("groups", {}).setdefault(group_id, {
                "group_id": group_id,
                "group_name": f"群組_{group_id[-6:]}",
                "expected_group_name": f"群組_{group_id[-6:]}",
                "sheet_tab": "三總保全內部群",
                "leader_email": "",
                "is_email_verified": False,
                "verified_leader_user_id": "",
                "pin_code": new_pin,
                "pin_updated_at": datetime.now().isoformat(),
                "is_unlocked": False,
                "unlocked_with_pin": ""
            })
            group["pin_code"] = new_pin
            group["pin_updated_at"] = datetime.now().isoformat()
            group["is_unlocked"] = False
            group["unlocked_with_pin"] = ""
            self._save_unsafe()
            return True

    def set_group_tab(self, group_id: str, tab_name: str) -> bool:
        with _lock:
            group = self.data.setdefault("groups", {}).setdefault(group_id, {
                "group_id": group_id,
                "group_name": f"群組_{group_id[-6:]}",
                "expected_group_name": f"群組_{group_id[-6:]}",
                "sheet_tab": tab_name,
                "leader_email": "",
                "is_email_verified": False,
                "verified_leader_user_id": "",
                "pin_code": settings.DEFAULT_PIN,
                "pin_updated_at": datetime.now().isoformat(),
                "is_unlocked": False,
                "unlocked_with_pin": ""
            })
            group["sheet_tab"] = tab_name
            self._save_unsafe()
            return True

    def verify_and_unlock(self, group_id: str, input_pin: str) -> bool:
        with _lock:
            groups = self.data.setdefault("groups", {})
            group = groups.get(group_id)
            if not group:
                group = {
                    "group_id": group_id,
                    "group_name": f"群組_{group_id[-6:]}",
                    "expected_group_name": f"群組_{group_id[-6:]}",
                    "sheet_tab": "三總保全內部群",
                    "leader_email": "",
                    "is_email_verified": False,
                    "verified_leader_user_id": "",
                    "pin_code": settings.DEFAULT_PIN,
                    "pin_updated_at": datetime.now().isoformat(),
                    "is_unlocked": False,
                    "unlocked_with_pin": ""
                }
                groups[group_id] = group

            expected_pin = group.get("pin_code", settings.DEFAULT_PIN)
            if input_pin.strip() == str(expected_pin).strip():
                group["is_unlocked"] = True
                group["unlocked_with_pin"] = input_pin.strip()
                self._save_unsafe()
                return True
            return False

    def verify_dual_pin(self, group_id: str, master_pin: str, sub_pin: str) -> bool:
        with _lock:
            current_master = self.data.get("master_pin", settings.MASTER_PIN)
            if master_pin.strip() != str(current_master).strip():
                return False

            group = self.data.get("groups", {}).get(group_id)
            if not group:
                return False

            expected_sub = group.get("pin_code", settings.DEFAULT_PIN)
            return sub_pin.strip() == str(expected_sub).strip()

    def is_group_unlocked(self, group_id: str) -> bool:
        with _lock:
            group = self.data.get("groups", {}).get(group_id)
            if not group:
                return False
            return group.get("is_unlocked", False) and (group.get("unlocked_with_pin") == group.get("pin_code"))

    def get_groups_by_tab(self, tab_name: str) -> List[Dict[str, Any]]:
        with _lock:
            groups = self.data.get("groups", {})
            return [g for g in groups.values() if g.get("sheet_tab") == tab_name]

    def add_schedule_change_logs(self, log_entries: List[Dict[str, Any]]):
        with _lock:
            if "schedule_change_logs" not in self.data:
                self.data["schedule_change_logs"] = []
            self.data["schedule_change_logs"].extend(log_entries)
            # Keep max 500 records
            if len(self.data["schedule_change_logs"]) > 500:
                self.data["schedule_change_logs"] = self.data["schedule_change_logs"][-500:]
            self._save_unsafe()

    def get_schedule_change_logs(self, limit: int = 100, tab_name: Optional[str] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
        from app.services.rare_char_helper import rare_char_harmonizer
        with _lock:
            logs = self.data.get("schedule_change_logs", [])
            q = (query or tab_name or "").strip().lower()
            if q:
                variants = rare_char_harmonizer.get_search_variants(q)
                filtered = []
                for l in logs:
                    text_corpus = f"{l.get('tab_name', '')} {l.get('member_name', '')} {l.get('post', '')} {l.get('shift_type', '')} {l.get('action', '')} {l.get('date', '')}".lower()
                    if any(v in text_corpus for v in variants):
                        filtered.append(l)
                logs = filtered
            return list(reversed(logs))[:limit]

    def is_master_pin_initialized(self) -> bool:
        with _lock:
            return bool(self.data.get("master_pin_initialized", False) and self.data.get("master_pin"))

    def reset_master_pin(self):
        with _lock:
            self.data["master_pin"] = None
            self.data["master_pin_initialized"] = False
            if "master_pin_history" not in self.data:
                self.data["master_pin_history"] = []
            self.data["master_pin_history"].append({
                "action": "RESET",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "note": "管理員重置 Master PIN，等待前端首次登入設定新密碼"
            })
            self._save_unsafe()

    def set_master_pin(self, new_pin: str, admin_email: str = "ericlai429@gmail.com") -> bool:
        with _lock:
            if not new_pin or len(new_pin.strip()) < 3:
                return False
            cleaned_pin = new_pin.strip()
            self.data["master_pin"] = cleaned_pin
            self.data["master_pin_initialized"] = True
            self.data["master_pin_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.data["master_pin_admin_email"] = admin_email.strip().lower()

            if "master_pin_history" not in self.data:
                self.data["master_pin_history"] = []
            self.data["master_pin_history"].append({
                "action": "SETUP",
                "admin_email": admin_email,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "note": f"管理員 {admin_email} 於前端首次成功設定專屬 Master PIN 碼"
            })
            self._save_unsafe()
            return True

    def verify_master_pin_auth(self, input_pin: str) -> bool:
        with _lock:
            saved_pin = self.data.get("master_pin")
            if not saved_pin:
                # If not initialized, fallback to default 789 or require setup
                return False
            return str(saved_pin).strip() == str(input_pin).strip()

    def get_schedule_snapshot(self, tab_name: str) -> List[List[str]]:
        with _lock:
            snapshots = self.data.get("schedule_snapshots", {})
            return snapshots.get(tab_name, [])

    def save_schedule_snapshot(self, tab_name: str, rows: List[List[str]]):
        with _lock:
            if "schedule_snapshots" not in self.data:
                self.data["schedule_snapshots"] = {}
            self.data["schedule_snapshots"][tab_name] = rows
            self._save_unsafe()

db = Database()

