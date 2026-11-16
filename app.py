"""Invoice Cloud Demo: Server-Side Input Validation."""

import json
import os
import uuid
import math

from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


# Configuration
INVOICE_DIR = Path(os.environ.get("INVOICE_DIR", "invoice"))
S3_BUCKET = os.environ.get("S3_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
APP_VERSION = os.environ.get("APP_VERSION", "v2")

# Create invoice folder if it does not exist
INVOICE_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


# Generate unique invoice ID
def new_invoice_id():
    now = datetime.now(timezone.utc)

    return f"INV-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


# Display validation error
def show_error(message):
    files = sorted(
        INVOICE_DIR.glob("*.json"),
        reverse=True
    )[:10]

    return render_template(
        "index.html",
        invoices=[f.name for f in files],
        message=f"Invalid invoice: {message}",
        bucket=S3_BUCKET or "not configured",
        version=APP_VERSION,
        host=os.environ.get("HOSTNAME", "local"),
    ), 400


# Upload invoice to S3
def upload_to_s3(file_path):

    if not S3_BUCKET:
        return "S3 not configured (local mode): file saved only in invoice folder"

    import boto3

    key = f"invoice/{file_path.name}"

    boto3.client(
        "s3",
        region_name=AWS_REGION
    ).upload_file(
        str(file_path),
        S3_BUCKET,
        key,
        ExtraArgs={"ContentType": "application/json"}
    )

    return f"Uploaded to s3://{S3_BUCKET}/{key}"


# Home page
@app.route("/")
def home():

    files = sorted(
        INVOICE_DIR.glob("*.json"),
        reverse=True
    )[:10]

    return render_template(
        "index.html",
        invoices=[f.name for f in files],
        message=request.args.get("message", ""),
        bucket=S3_BUCKET or "not configured",
        version=APP_VERSION,
        host=os.environ.get("HOSTNAME", "local"),
    )


# Create invoice
@app.route("/invoice", methods=["POST"])
def create_invoice():

    # Get input values
    customer = request.form.get("customer", "").strip()
    item = request.form.get("item", "Item").strip()

    # 1. Validate customer name
    if len(customer) < 3:
        return show_error(
            "Customer name must be at least 3 characters"
        )

    # 2. Validate quantity
    try:
        quantity = int(request.form.get("quantity", ""))

    except (ValueError, TypeError):
        return show_error(
            "Quantity must be a valid number"
        )

    if quantity < 1 or quantity > 100:
        return show_error(
            "Quantity must be between 1 and 100"
        )

    # 3. Validate unit price
    try:
        unit_price = float(request.form.get("unit_price", ""))

    except (ValueError, TypeError):
        return show_error(
            "Unit price must be a valid number"
        )

    if not math.isfinite(unit_price) or not (0 < unit_price <= 100000):
        return show_error(
            "Unit price must be greater than 0 and at most 100000"
        )

    # All validations passed
    # Now create the invoice
    invoice = {
        "invoice_id": new_invoice_id(),
        "created_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "customer": customer,
        "email": request.form.get("email", "").strip(),
        "item": item,
        "quantity": quantity,
        "unit_price": unit_price,
        "amount": round(quantity * unit_price, 2),
    }

    # Save invoice locally
    file_path = INVOICE_DIR / f"{invoice['invoice_id']}.json"

    file_path.write_text(
        json.dumps(invoice, indent=2),
        encoding="utf-8"
    )

    # Upload invoice to S3
    try:
        status = upload_to_s3(file_path)

    except Exception as err:
        status = f"Saved locally, but S3 upload failed: {err}"

    # Show success message
    return redirect(
        url_for(
            "home",
            message=f"{file_path.name} created. {status}"
        )
    )


# Run Flask application
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )