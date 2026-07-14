from __future__ import annotations

from datetime import date


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\;", ";").replace("\\,", ",").replace("\\\\", "\\")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def parse_vcards(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in text.split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)

    cards: list[dict] = []
    current: dict[str, str] | None = None
    for line in lines:
        upper = line.upper()
        if upper == "BEGIN:VCARD":
            current = {}
            continue
        if upper == "END:VCARD":
            if current is None:
                continue
            name = current.get("FN") or current.get("N", "").replace(";", " ").strip()
            if name:
                birthday = current.get("BDAY", "")
                try:
                    birthday = date.fromisoformat(birthday).isoformat() if "-" in birthday else date(int(birthday[:4]), int(birthday[4:6]), int(birthday[6:8])).isoformat()
                except (TypeError, ValueError):
                    birthday = ""
                adr = current.get("ADR", "").split(";")
                cards.append({
                    "name": _unescape(name),
                    "email": _unescape(current.get("EMAIL", "")),
                    "phone": _unescape(current.get("TEL", "")),
                    "address": _unescape(adr[2]) if len(adr) > 2 else "",
                    "city": _unescape(adr[3]) if len(adr) > 3 else "",
                    "postal_code": _unescape(adr[5]) if len(adr) > 5 else "",
                    "notes": _unescape(current.get("NOTE", "")),
                    "birth_date": birthday,
                })
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()
        if key in {"FN", "N", "EMAIL", "TEL", "ADR", "NOTE", "BDAY"} and key not in current:
            current[key] = value
    return cards


def contacts_as_vcard(contacts) -> str:
    cards = []
    for contact in contacts:
        people = list(contact.people.all()) or [None]
        for person in people:
            name = person.name if person else contact.name
            email = person.email if person and person.email else contact.email
            phone = person.phone if person and person.phone else contact.phone
            lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_escape(name)}", f"N:{_escape(name)};;;;"]
            if email:
                lines.append(f"EMAIL;TYPE=INTERNET:{_escape(email)}")
            if phone:
                lines.append(f"TEL;TYPE=CELL:{_escape(phone)}")
            if contact.address or contact.city or contact.postal_code:
                lines.append(f"ADR;TYPE=HOME:;;{_escape(contact.address)};{_escape(contact.city)};;{_escape(contact.postal_code)};")
            if person and person.birth_date:
                lines.append(f"BDAY:{person.birth_date.isoformat()}")
            if contact.notes:
                lines.append(f"NOTE:{_escape(contact.notes)}")
            lines.append("END:VCARD")
            cards.append("\r\n".join(lines))
    return "\r\n".join(cards) + ("\r\n" if cards else "")
