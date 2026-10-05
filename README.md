# Raremotion Invoice

Invoice V1 by Raremotion Labs: business and customer details, multiple products/services, automatic subtotal and tax, NGN/USD/GBP/EUR, Paid/Unpaid status, and PDF export.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

Port 8502 keeps Invoice separate from other local apps.

## Download an invoice

1. Enter a business name, customer name, and at least one described item with a price above zero.
2. Finish editing the invoice and click **Prepare Invoice PDF**.
3. Click **Download Invoice PDF**.

Changes invalidate the prepared PDF; prepare it again after editing. PDFs stay in the current user's session memory, and invoices are not saved to a shared database. Payment status is a manual label.

## Deploy on Streamlit Community Cloud

Connect this repository, select branch `main`, set the entrypoint to `app.py`, and choose Python 3.12 or newer. Dependencies are pinned in `requirements.txt`; font files must be included. No secrets are required.

## Validation

One browser functional test on 5 October 2026 downloaded and visually checked a PDF for Raremotion Labs / Test Client: Website Development, quantity 2 × NGN 50,000; subtotal NGN 100,000; tax 7.5% / NGN 7,500; total NGN 107,500; Unpaid. The naira symbol and all expected details were verified in the downloaded file.

## Fonts

Bundled DejaVu Sans fonts provide currency-symbol support. See `assets/fonts/LICENSE.txt` for their license.
