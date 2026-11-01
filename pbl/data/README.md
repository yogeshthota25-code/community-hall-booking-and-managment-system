# Sample Booking Dataset

`sample_bookings.csv` contains 12 synthetic function-hall bookings for testing imports, dashboards, payment summaries, and reports. Names, addresses, email domains, booking references, and payment references are fictitious. Zero-filled phone numbers are placeholders, not contact details.

The CSV is not loaded into the live database automatically. Import it only into a development copy, and do not treat its payment records as real transactions.

`hall_amount` is the capacity-based hall estimate, `catering_amount` is the catering estimate, and `amount` is their total, all in INR. The demo rates are ₹10,000 for up to 250 guests, plus ₹5,000 per additional 250-guest tier; vegetarian catering is ₹250 per guest. These are configurable example rates, not confirmed venue tariffs. `amount_paid` is the recorded amount received; `payment_status` is `Unpaid`, `Partially Paid`, or `Paid`. `status` is the reservation review status (`Pending`, `Approved`, `Rejected`, or `Cancelled`).
