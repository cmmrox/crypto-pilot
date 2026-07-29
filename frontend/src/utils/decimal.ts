function incrementDigits(value: string): string {
  const digits = value.split("");
  for (let index = digits.length - 1; index >= 0; index -= 1) {
    if (digits[index] !== "9") {
      digits[index] = String(Number(digits[index]) + 1);
      return digits.join("");
    }
    digits[index] = "0";
  }
  return `1${digits.join("")}`;
}

function decimalParts(value: string) {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  return {
    negative: match[1] === "-",
    integer: match[2].replace(/^0+(?=\d)/, ""),
    fraction: match[3] ?? "",
  };
}

export function isNegativeDecimal(value: string | null | undefined): boolean {
  if (!value) return false;
  const parts = decimalParts(value);
  return Boolean(parts?.negative && /[1-9]/.test(`${parts.integer}${parts.fraction}`));
}

export function isPositiveDecimal(value: string | null | undefined): boolean {
  if (!value) return false;
  const parts = decimalParts(value);
  return Boolean(parts && !parts.negative && /[1-9]/.test(`${parts.integer}${parts.fraction}`));
}

export function formatDecimal(value: string, fractionDigits = 2): string {
  const parts = decimalParts(value);
  if (!parts) return value;

  const paddedFraction = parts.fraction.padEnd(fractionDigits + 1, "0");
  const keptFraction = paddedFraction.slice(0, fractionDigits);
  let combined = `${parts.integer}${keptFraction}`;
  if (paddedFraction[fractionDigits] >= "5") combined = incrementDigits(combined);
  combined = combined.padStart(fractionDigits + 1, "0");

  const integer = fractionDigits === 0 ? combined : combined.slice(0, -fractionDigits);
  const fraction = fractionDigits === 0 ? "" : combined.slice(-fractionDigits);
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const isZero = !/[1-9]/.test(combined);

  return `${parts.negative && !isZero ? "-" : ""}${grouped}${
    fractionDigits > 0 ? `.${fraction}` : ""
  }`;
}

export function formatUsd(value: string, fractionDigits = 2): string {
  const formatted = formatDecimal(value, fractionDigits);
  return formatted.startsWith("-") ? `-$${formatted.slice(1)}` : `$${formatted}`;
}
