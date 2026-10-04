# The automatic checks

After reading an invoice, InvoiceFlow does not simply trust the result. It re-calculates the numbers itself and flags anything that does not add up.

## Line item check

For each line, quantity multiplied by unit price must equal the line amount.

## Totals check

The line amounts must add up to the subtotal. If there is no subtotal on the invoice, the line amounts plus tax must equal the total. Separately, subtotal plus tax must equal the total. If tax is not printed, it is treated as zero.

## Required fields

Vendor, invoice date, invoice number and total must be present. If one is missing or unreadable, it is flagged. The total must also be greater than zero.

## Rounding tolerance

Numbers are allowed to differ by up to 0.02, so ordinary rounding does not cause false alarms.

## Why checks matter

A reading mistake, such as a misread digit, almost never still adds up. Re-checking the arithmetic catches most reading errors without you having to look at every invoice.

## Server-side

The checks run again every time you save an edit. The review screen cannot be used to skip them.
