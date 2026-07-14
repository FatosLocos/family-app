import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { parseAbnAmroStatement, parseAbnAmroWorkbook } from "./abn-amro-import";

describe("parseAbnAmroStatement", () => {
  it("parses semicolon separated ABN AMRO transaction exports", () => {
    const csv = [
      "Rekening;NL12ABNA0123456789",
      "Boekdatum;Omschrijving;Tegenrekening naam;Bedrag;Muntsoort",
      "13-07-2026;ALBERT HEIJN 1234;AH Winkel;-12,34;EUR",
      "12-07-2026;Salaris juli;Werkgever;2500,00;EUR",
      "geen datum;Onvolledig;Test;1,00;EUR",
    ].join("\n");

    const result = parseAbnAmroStatement(csv, "ABN prive");

    expect(result.iban).toBe("NL12ABNA0123456789");
    expect(result.accountName).toBe("ABN AMRO 6789");
    expect(result.skippedRows).toBe(1);
    expect(result.transactions).toHaveLength(2);
    expect(result.transactions[0]).toMatchObject({
      bookedAt: "2026-07-13T00:00:00.000Z",
      description: "ALBERT HEIJN 1234",
      counterparty: "AH Winkel",
      amountCents: -1234,
      currency: "EUR",
    });
    expect(result.transactions[1]?.amountCents).toBe(250000);
  });

  it("parses Excel statement workbooks", () => {
    const workbook = XLSX.utils.book_new();
    const worksheet = XLSX.utils.aoa_to_sheet([
      ["Rekening", "NL12ABNA0123456789"],
      ["Boekdatum", "Omschrijving", "Tegenrekening naam", "Bedrag", "Muntsoort"],
      ["13-07-2026", "JUMBO SUPERMARKT", "Jumbo", "-45,67", "EUR"],
    ]);
    XLSX.utils.book_append_sheet(workbook, worksheet, "Afschrift");
    const buffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as ArrayBuffer;

    const result = parseAbnAmroWorkbook(buffer, "ABN prive");

    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0]).toMatchObject({
      bookedAt: "2026-07-13T00:00:00.000Z",
      description: "JUMBO SUPERMARKT",
      amountCents: -4567,
    });
  });

  it("recognizes ABN Excel headers with Af/Bij and Bedrag EUR columns", () => {
    const workbook = XLSX.utils.book_new();
    const worksheet = XLSX.utils.aoa_to_sheet([
      ["ABN AMRO mutatieoverzicht"],
      ["Datum", "Naam / Omschrijving", "Tegenrekening naam", "Af/Bij", "Bedrag (EUR)"],
      ["13-07-26", "LIDL", "Lidl Nederland", "Af", "19,95"],
      ["12-07-26", "Salaris", "Werkgever", "Bij", "2500,00"],
    ]);
    XLSX.utils.book_append_sheet(workbook, worksheet, "Mutaties");
    const buffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as ArrayBuffer;

    const result = parseAbnAmroWorkbook(buffer, "ABN prive");

    expect(result.transactions).toHaveLength(2);
    expect(result.transactions[0]?.amountCents).toBe(-1995);
    expect(result.transactions[1]?.amountCents).toBe(250000);
  });

  it("parses ABN exports with rekeningnummer, muntsoort, transactiedatum and transactiebedrag", () => {
    const csv = [
      "Rekeningnummer\tMuntsoort\tTransactiedatum\tRentedatum\tBeginsaldo\tEindsaldo\tTransactiebedrag\tOmschrijving",
      "NL12ABNA0123456789\tEUR\t13-07-2026\t13-07-2026\t1000,00\t987,66\t-12,34\tALBERT HEIJN",
      "NL12ABNA0123456789\tEUR\t12-07-2026\t12-07-2026\t987,66\t3487,66\t2500,00\tSalaris",
    ].join("\n");

    const result = parseAbnAmroStatement(csv, "ABN prive");

    expect(result.iban).toBe("NL12ABNA0123456789");
    expect(result.transactions).toHaveLength(2);
    expect(result.transactions[0]).toMatchObject({
      bookedAt: "2026-07-13T00:00:00.000Z",
      description: "ALBERT HEIJN",
      amountCents: -1234,
    });
    expect(result.transactions[1]?.amountCents).toBe(250000);
  });

  it("parses ABN savings export rows with compact dates and numeric account number", () => {
    const csv = [
      "Rekeningnummer\tMuntsoort\tTransactiedatum\tRentedatum\tBeginsaldo\tEindsaldo\tTransactiebedrag\tOmschrijving",
      "473586657\tEUR\t20260103\t20251231\t14720,90\t14774,80\t53,90\tRENTE EN/OF KOSTEN CREDITRENTE 53,90C van 30.09.2025 tot 31.12.2025 DIRECT SPAREN",
    ].join("\n");

    const result = parseAbnAmroStatement(csv, "ABN sparen");

    expect(result.accountIdentifier).toBe("473586657");
    expect(result.accountName).toBe("ABN AMRO 6657");
    expect(result.iban).toBeNull();
    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0]).toMatchObject({
      bookedAt: "2026-01-03T00:00:00.000Z",
      amountCents: 5390,
      currency: "EUR",
    });
  });

  it("keeps extra tab separated ABN description fields", () => {
    const csv = [
      "Rekeningnummer\tMuntsoort\tTransactiedatum\tRentedatum\tBeginsaldo\tEindsaldo\tTransactiebedrag\tOmschrijving",
      "473586657\tEUR\t20260710\t20260710\t100,00\t96,73\t-3,27\tBEA, Apple Pay JUMBO BOGAARD\tPAS474\tNR:29N002\t10.07.26/12:23",
    ].join("\n");

    const result = parseAbnAmroStatement(csv, "ABN prive");

    expect(result.transactions[0]?.description).toContain("PAS474");
    expect(result.transactions[0]?.description).toContain("NR:29N002");
    expect(result.transactions[0]?.description).toContain("10.07.26/12:23");
    expect(result.transactions[0]?.raw.extra_1).toBe("PAS474");
  });

  it("parses Excel serial dates and scans all workbook sheets", () => {
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([["Samenvatting"], ["Geen transacties"]]), "Voorblad");
    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.aoa_to_sheet([
        ["Rekeningnummer", "Muntsoort", "Transactiedatum", "Rentedatum", "Beginsaldo", "Eindsaldo", "Transactiebedrag", "Omschrijving"],
        ["NL12ABNA0123456789", "EUR", 46216, 46216, "1000,00", "987,66", -12.34, "ALBERT HEIJN"],
      ]),
      "Mutaties",
    );
    const buffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as ArrayBuffer;

    const result = parseAbnAmroWorkbook(buffer, "ABN prive");

    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0]).toMatchObject({
      bookedAt: "2026-07-13T00:00:00.000Z",
      amountCents: -1234,
      description: "ALBERT HEIJN",
    });
  });
});
