# Uploading files

## Supported file types

InvoiceFlow accepts PDF, PNG, JPEG and WebP files. Other file types, such as Word documents or spreadsheets, are rejected with a message saying only PDF, PNG, JPEG or WebP files are allowed.

## File size limit

Each file can be up to 10 MB. A larger file is rejected with a message that names the file and the limit. If your scan is too big, re-save it at a lower resolution or compress the PDF and upload it again.

## File type is checked, not just the extension

InvoiceFlow looks at the contents of the file, not only its name or declared type. A file renamed from .txt to .pdf will be rejected.

## PDFs with many pages

Only the first two pages of a PDF are read. If an invoice runs longer than two pages, the extracted fields come from those first two pages, so check the totals during review.

## Uploading many files

You can select several files in one go. Each becomes its own invoice and is processed separately, so one failed file does not stop the others.
