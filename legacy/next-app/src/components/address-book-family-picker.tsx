"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

type FamilyOption = {
  id: string;
  name: string;
  relationship: string | null;
};

export function AddressBookFamilyPicker({ contacts }: { contacts: FamilyOption[] }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const matches = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("nl-NL");
    if (!normalized) return contacts.slice(0, 6);
    return contacts.filter((contact) => `${contact.name} ${contact.relationship ?? ""}`.toLocaleLowerCase("nl-NL").includes(normalized)).slice(0, 6);
  }, [contacts, query]);

  function choose(contact: FamilyOption) {
    setSelectedId(contact.id);
    setQuery(contact.name);
    setIsOpen(false);
  }

  return (
    <div className="addressbook-family-picker">
      <input type="hidden" name="contact_id" value={selectedId} />
      <div className="input-with-icon">
        <Search size={16} />
        <input
          id="addressbook-member-family"
          type="search"
          placeholder="Zoek een familie"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelectedId("");
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}
          role="combobox"
          aria-autocomplete="list"
          aria-controls="addressbook-family-options"
          aria-expanded={isOpen}
        />
      </div>
      {isOpen && (
        <div className="addressbook-family-options" id="addressbook-family-options" role="listbox">
          {matches.length === 0 && <span>Geen familie gevonden.</span>}
          {matches.map((contact) => (
            <button key={contact.id} type="button" role="option" aria-selected={selectedId === contact.id} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(contact)}>
              <strong>{contact.name}</strong>
              {contact.relationship && <small>{contact.relationship}</small>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
