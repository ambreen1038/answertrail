# Invoice statuses

Every invoice moves through a short set of statuses, shown in the dashboard table.

## The status flow

An invoice goes queued, then processing, then needs review, then approved. It can also end as failed.

- **Queued**: the file is uploaded and waiting its turn to be read.
- **Processing**: the app is reading the fields and running its checks.
- **Needs review**: the fields were read, but at least one check failed or a field is missing. A person should look at it.
- **Approved**: you reviewed it and accepted it. Only approved invoices are included in exports.
- **Failed**: the file could not be read even after several automatic retries.

## Automatic retries

If reading a file fails, InvoiceFlow tries again automatically, up to three attempts in total, waiting a little longer between each attempt. If an attempt is interrupted, for example by a restart, the job is picked up again. If all attempts fail, the invoice is marked failed.

## What to do with a failed invoice

Delete it and upload the file again, ideally a clearer scan or photo. If it keeps failing, check that the file opens normally and is a real invoice.
