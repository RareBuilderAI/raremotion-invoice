import streamlit as st
from functools import partial
from accounts import require_account, PdfDelivery, EXHAUSTED_MESSAGE
from io import BytesIO
from html import escape
from pathlib import Path
from copy import deepcopy
import re
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Raremotion Invoice",
    page_icon="🧾",
    layout="wide",
)


# ---------------------------------------------------------
# CUSTOM DESIGN
# ---------------------------------------------------------

st.markdown(
    """
    <style>
        .stApp {
            background-color: #0d1117;
            color: #f5f5f5;
        }

        .block-container {
            max-width: 1200px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        .rm-badge {
            display: inline-block;
            padding: 6px 12px;
            border: 1px solid #30363d;
            border-radius: 999px;
            color: #b8c0cc;
            font-size: 12px;
            letter-spacing: 1.5px;
            margin-bottom: 15px;
        }

        .rm-title {
            font-size: 46px;
            font-weight: 800;
            margin-bottom: 5px;
        }

        .rm-subtitle {
            color: #9da7b3;
            font-size: 17px;
            margin-bottom: 30px;
        }

        .summary-card {
            border: 1px solid #30363d;
            background: #161b22;
            border-radius: 14px;
            padding: 20px;
            margin-top: 10px;
        }

        div[data-testid="stMetric"] {
            background: #161b22;
            border: 1px solid #30363d;
            padding: 16px;
            border-radius: 12px;
        }

        div[data-testid="stForm"] {
            border: 1px solid #30363d;
            border-radius: 16px;
            padding: 22px;
            background: #11161d;
        }

        .invoice-status {
            display: inline-block;
            padding: 7px 15px;
            border-radius: 999px;
            border: 1px solid #30363d;
            font-weight: 700;
            margin-bottom: 15px;
        }

        footer {
            visibility: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


accounts, account_token, trial_used = require_account()
if "pdf_delivery" not in st.session_state:
    st.session_state.pdf_delivery = PdfDelivery()


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

if "invoice_items" not in st.session_state:
    st.session_state.invoice_items = [
        {
            "description": "",
            "quantity": 1,
            "price": 0.0,
        }
    ]


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def money(value, currency):
    return f"{currency}{value:,.2f}"


def create_invoice_pdf(invoice):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    font_dir = Path(__file__).parent / "assets" / "fonts"
    for name, filename in (("InvoiceSans", "DejaVuSans.ttf"), ("InvoiceSans-Bold", "DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily("InvoiceSans", normal="InvoiceSans", bold="InvoiceSans-Bold", italic="InvoiceSans", boldItalic="InvoiceSans-Bold")
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "InvoiceSans"
    # ReportLab paragraphs interpret markup; keep user-entered text literal.
    invoice = deepcopy(invoice)
    for key, value in invoice.items():
        if isinstance(value, str):
            invoice[key] = escape(value).replace("\n", "<br/>")

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=27,
        spaceAfter=8,
    )

    right_style = ParagraphStyle(
        "Right",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=10,
        leading=15,
    )

    story = []

    header = Table(
        [
            [
                Paragraph(
                    f"<b>{invoice['business_name']}</b><br/>"
                    f"{invoice['business_email']}<br/>"
                    f"{invoice['business_phone']}<br/>"
                    f"{invoice['business_address']}",
                    styles["Normal"],
                ),
                Paragraph(
                    "<b>RAREMOTION INVOICE</b>",
                    title_style,
                ),
            ]
        ],
        colWidths=[95 * mm, 75 * mm],
    )

    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )

    story.append(header)
    story.append(Spacer(1, 12))

    details = Table(
        [
            [
                Paragraph(
                    "<b>BILL TO</b><br/><br/>"
                    f"{invoice['customer_name']}<br/>"
                    f"{invoice['customer_email']}<br/>"
                    f"{invoice['customer_address']}",
                    styles["Normal"],
                ),
                Paragraph(
                    f"<b>Invoice:</b> {invoice['invoice_number']}<br/>"
                    f"<b>Issue date:</b> {invoice['issue_date']}<br/>"
                    f"<b>Due date:</b> {invoice['due_date']}<br/>"
                    f"<b>Status:</b> {invoice['status']}",
                    right_style,
                ),
            ]
        ],
        colWidths=[95 * mm, 75 * mm],
    )

    details.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story.append(details)
    story.append(Spacer(1, 24))

    item_rows = [
        [
            "Description",
            "Quantity",
            "Unit Price",
            "Amount",
        ]
    ]

    for item in invoice["items"]:
        item_rows.append(
            [
                Paragraph(escape(item["description"]).replace("\n", "<br/>"), styles["Normal"]),
                str(item["quantity"]),
                money(item["price"], invoice["currency"]),
                money(
                    item["quantity"] * item["price"],
                    invoice["currency"],
                ),
            ]
        )

    items_table = Table(
        item_rows,
        colWidths=[
            80 * mm,
            25 * mm,
            32 * mm,
            33 * mm,
        ],
    )

    items_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "InvoiceSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#111827"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "InvoiceSans-Bold",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#d1d5db"),
                ),
                (
                    "ALIGN",
                    (1, 1),
                    (-1, -1),
                    "RIGHT",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 18))

    totals = Table(
        [
            [
                "Subtotal",
                money(
                    invoice["subtotal"],
                    invoice["currency"],
                ),
            ],
            [
                f"Tax ({invoice['tax_rate']:.2f}%)",
                money(
                    invoice["tax_amount"],
                    invoice["currency"],
                ),
            ],
            [
                "TOTAL",
                money(
                    invoice["total"],
                    invoice["currency"],
                ),
            ],
        ],
        colWidths=[45 * mm, 40 * mm],
        hAlign="RIGHT",
    )

    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "InvoiceSans"),
                (
                    "ALIGN",
                    (1, 0),
                    (1, -1),
                    "RIGHT",
                ),
                (
                    "FONTNAME",
                    (0, -1),
                    (-1, -1),
                    "InvoiceSans-Bold",
                ),
                (
                    "LINEABOVE",
                    (0, -1),
                    (-1, -1),
                    1,
                    colors.black,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ]
        )
    )

    story.append(totals)
    story.append(Spacer(1, 25))

    if invoice["notes"]:
        story.append(
            Paragraph(
                "<b>Notes</b>",
                styles["Heading3"],
            )
        )

        story.append(
            Paragraph(
                invoice["notes"],
                styles["Normal"],
            )
        )

    story.append(Spacer(1, 30))

    story.append(
        Paragraph(
            "Generated with Raremotion Invoice",
            styles["Normal"],
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer.getvalue()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.markdown(
    '<div class="rm-badge">RAREMOTION LABS</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="rm-title">Raremotion Invoice</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="rm-subtitle">
        Create professional invoices, calculate totals,
        track payment status and export them as PDF.
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# BUSINESS + CUSTOMER DETAILS
# ---------------------------------------------------------

st.subheader("Invoice Details")

left, right = st.columns(2)

with left:
    st.markdown("#### Your Business")

    business_name = st.text_input(
        "Business name",
        placeholder="Raremotion Labs",
    )

    business_email = st.text_input(
        "Business email",
        placeholder="hello@example.com",
    )

    business_phone = st.text_input(
        "Business phone",
        placeholder="+234...",
    )

    business_address = st.text_area(
        "Business address",
        placeholder="Business address",
        height=100,
    )

with right:
    st.markdown("#### Customer")

    customer_name = st.text_input(
        "Customer name",
        placeholder="Customer or company name",
    )

    customer_email = st.text_input(
        "Customer email",
        placeholder="customer@example.com",
    )

    customer_address = st.text_area(
        "Customer address",
        placeholder="Customer billing address",
        height=100,
    )


# ---------------------------------------------------------
# INVOICE INFORMATION
# ---------------------------------------------------------

st.divider()
st.subheader("Invoice Information")

col1, col2, col3, col4 = st.columns(4)

with col1:
    invoice_number = st.text_input(
        "Invoice number",
        value=f"INV-{date.today().strftime('%Y%m%d')}-001",
    )

with col2:
    issue_date = st.date_input(
        "Issue date",
        value=date.today(),
    )

with col3:
    due_date = st.date_input(
        "Due date",
        value=date.today() + timedelta(days=14),
    )

with col4:
    status = st.selectbox(
        "Payment status",
        [
            "Unpaid",
            "Paid",
        ],
    )


# ---------------------------------------------------------
# CURRENCY + TAX
# ---------------------------------------------------------

currency_col, tax_col = st.columns(2)

with currency_col:
    currency_name = st.selectbox(
        "Currency",
        [
            "NGN — Nigerian Naira",
            "USD — US Dollar",
            "GBP — British Pound",
            "EUR — Euro",
        ],
    )

currency_symbols = {
    "NGN — Nigerian Naira": "₦",
    "USD — US Dollar": "$",
    "GBP — British Pound": "£",
    "EUR — Euro": "€",
}

currency = currency_symbols[currency_name]

with tax_col:
    tax_rate = st.number_input(
        "Tax (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
    )


# ---------------------------------------------------------
# ITEMS
# ---------------------------------------------------------

st.divider()
st.subheader("Products / Services")

updated_items = []

for index, item in enumerate(st.session_state.invoice_items):
    c1, c2, c3 = st.columns([5, 1.5, 2])

    with c1:
        description = st.text_input(
            "Description",
            value=item["description"],
            key=f"description_{index}",
            placeholder="Website development",
        )

    with c2:
        quantity = st.number_input(
            "Quantity",
            min_value=1,
            value=int(item["quantity"]),
            step=1,
            key=f"quantity_{index}",
        )

    with c3:
        price = st.number_input(
            "Unit price",
            min_value=0.0,
            value=float(item["price"]),
            step=100.0,
            key=f"price_{index}",
        )

    updated_items.append(
        {
            "description": description,
            "quantity": quantity,
            "price": price,
        }
    )

st.session_state.invoice_items = updated_items


add_col, remove_col = st.columns(2)

with add_col:
    if st.button(
        "＋ Add Item",
        use_container_width=True,
    ):
        st.session_state.invoice_items.append(
            {
                "description": "",
                "quantity": 1,
                "price": 0.0,
            }
        )

        st.rerun()

with remove_col:
    if st.button(
        "− Remove Last Item",
        use_container_width=True,
        disabled=len(st.session_state.invoice_items) <= 1,
    ):
        st.session_state.invoice_items.pop()

        st.rerun()


# ---------------------------------------------------------
# CALCULATIONS
# ---------------------------------------------------------

subtotal = sum(
    item["quantity"] * item["price"]
    for item in st.session_state.invoice_items
)

tax_amount = subtotal * (tax_rate / 100)

total = subtotal + tax_amount


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

st.divider()
st.subheader("Invoice Summary")

metric1, metric2, metric3 = st.columns(3)

metric1.metric(
    "Subtotal",
    money(subtotal, currency),
)

metric2.metric(
    f"Tax ({tax_rate:.2f}%)",
    money(tax_amount, currency),
)

metric3.metric(
    "Total",
    money(total, currency),
)


# ---------------------------------------------------------
# NOTES
# ---------------------------------------------------------

notes = st.text_area(
    "Notes / Payment Instructions",
    placeholder=(
        "Thank you for your business. "
        "Payment is due within 14 days."
    ),
)


# ---------------------------------------------------------
# PDF GENERATION
# ---------------------------------------------------------

st.divider()

invoice_data = {
    "business_name": business_name or "Your Business",
    "business_email": business_email,
    "business_phone": business_phone,
    "business_address": business_address,
    "customer_name": customer_name or "Customer",
    "customer_email": customer_email,
    "customer_address": customer_address,
    "invoice_number": invoice_number,
    "issue_date": issue_date.strftime("%d %B %Y"),
    "due_date": due_date.strftime("%d %B %Y"),
    "status": status,
    "currency": currency,
    "tax_rate": tax_rate,
    "subtotal": subtotal,
    "tax_amount": tax_amount,
    "total": total,
    "items": st.session_state.invoice_items,
    "notes": notes,
}




# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

has_priced_item = any(
    item["description"].strip() and item["price"] > 0
    for item in st.session_state.invoice_items
)
invoice_ready = bool(business_name.strip()) and bool(customer_name.strip()) and has_priced_item

missing = []
if not business_name.strip():
    missing.append("business name")
if not customer_name.strip():
    missing.append("customer name")
if not has_priced_item:
    missing.append("a product or service with a description and a price above zero")
if missing:
    st.info("To prepare your invoice, add: " + "; ".join(missing) + ".")

# Keep a completed snapshot in this user's session, never a shared cache.
# Editing any field invalidates the snapshot so an older invoice cannot download.
if st.session_state.get("prepared_invoice") != invoice_data:
    st.session_state.pop("prepared_pdf", None)
    st.session_state.pop("prepared_invoice", None)

if st.button("Prepare Invoice PDF", use_container_width=True, disabled=not invoice_ready):
    try:
        st.session_state.prepared_pdf = create_invoice_pdf(invoice_data)
        st.session_state.prepared_invoice = deepcopy(invoice_data)
    except Exception:
        st.error("The PDF could not be prepared. Your invoice details are still here. Please review them and try again.")

pdf = st.session_state.get("prepared_pdf")
if pdf:
    st.success("Your invoice PDF is ready. Click Download Invoice PDF to save it.")
elif invoice_ready:
    st.caption("Click Prepare Invoice PDF, then download your completed invoice.")

st.caption("Your account includes exactly 2 free PDF downloads. Each download counts, even for the same invoice. Preparing or editing an invoice is free.")

@st.fragment(run_every="2s")
def download_controls():
    delivery = st.session_state.pdf_delivery
    used, message = delivery.status()
    used = max(trial_used, used or 0)
    st.caption(f"{max(0, 2 - used)} of 2 free PDF downloads remaining")
    if used >= 2:
        st.warning(EXHAUSTED_MESSAGE)
    elif message:
        st.error(message)
    # Never give the widget unguarded PDF bytes. Every click invokes the server
    # callback, which checks the verified account and claims a database slot.
    snapshot = st.session_state.get("prepared_pdf")
    safe_number = re.sub(r"[^\w.-]+", "_", invoice_number).strip("._") or "invoice"
    st.download_button(
        "Download Invoice PDF",
        data=partial(delivery.download, accounts, account_token, snapshot),
        file_name=f"{safe_number}.pdf",
        mime="application/pdf",
        use_container_width=True,
        disabled=snapshot is None or used >= 2,
        on_click="ignore",
    )
    if st.button("Refresh download allowance"):
        st.rerun(scope="app")

download_controls()


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.markdown(
    """
    <br><br>
    <div style="
        text-align:center;
        color:#6e7681;
        font-size:13px;
    ">
        Raremotion Invoice • Built by Raremotion Labs
    </div>
    """,
    unsafe_allow_html=True,
)