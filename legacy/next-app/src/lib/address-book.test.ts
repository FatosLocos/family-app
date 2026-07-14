import { describe, expect, it } from "vitest";
import { exportAddressBookVCard, parseAddressBookFile } from "./address-book";

describe("address book import and export", () => {
  it("imports CSV contacts with address and birth date", () => {
    const result = parseAddressBookFile(
      [
        "Naam;Telefoon;E-mail;Adres;Postcode;Plaats;Land;Geboortedatum",
        "Familie Jansen;0612345678;familie@example.test;Voorbeeldstraat 1;1234 AB;Zoetermeer;Nederland;1988-07-14",
      ].join("\n"),
      "contacten.csv",
    );

    expect(result).toEqual([expect.objectContaining({
      name: "Familie Jansen",
      phone: "0612345678",
      city: "Zoetermeer",
      birthDate: "1988-07-14",
    })]);
  });

  it("imports vCard contacts", () => {
    const result = parseAddressBookFile(
      [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "FN:Roxane Voorbeeld",
        "TEL:0612345678",
        "EMAIL:roxane@example.test",
        "ADR:;;Voorbeeldstraat 1;Zoetermeer;;1234 AB;Nederland",
        "BDAY:19910725",
        "END:VCARD",
      ].join("\r\n"),
      "contact.vcf",
    );

    expect(result).toEqual([expect.objectContaining({
      name: "Roxane Voorbeeld",
      postalCode: "1234 AB",
      birthDate: "1991-07-25",
    })]);
  });

  it("exports contact groups and their members as vCards", () => {
    const output = exportAddressBookVCard(
      [{
        id: "contact-1",
        household_id: "household-1",
        name: "Familie Jansen",
        contact_type: "gezin",
        relationship: "Familie",
        phone: "0612345678",
        email: null,
        address: "Voorbeeldstraat 1",
        postal_code: "1234 AB",
        city: "Zoetermeer",
        country: "Nederland",
        notes: null,
        priority: "normaal",
      }],
      [{
        id: "member-1",
        household_id: "household-1",
        contact_id: "contact-1",
        name: "Sam Jansen",
        relationship: "Kind",
        birth_date: "2018-07-20",
        phone: null,
        email: null,
        notes: null,
      }],
    );

    expect(output).toContain("FN:Familie Jansen");
    expect(output).toContain("FN:Sam Jansen");
    expect(output).toContain("BDAY:2018-07-20");
  });
});
