const bookingForm = document.querySelector('.booking-form[data-base-hall-rate]');

if (bookingForm) {
    const guestInput = document.getElementById('guests');
    const cateringSelect = document.getElementById('catering_option');
    const quoteTotal = document.getElementById('quote-total');
    const quoteNote = document.getElementById('quote-note');
    const hallAmount = document.getElementById('hall-amount');
    const cateringAmount = document.getElementById('catering-amount');
    const summaryTotal = document.getElementById('summary-total');
    const paymentNote = document.getElementById('payment-quote-note');
    const formatter = new Intl.NumberFormat('en-IN');
    const baseHallRate = Number(bookingForm.dataset.baseHallRate);
    const tierSize = Number(bookingForm.dataset.tierSize);
    const tierIncrement = Number(bookingForm.dataset.tierIncrement);
    const cateringRate = Number(bookingForm.dataset.cateringRate);
    const maximumGuests = Number(bookingForm.dataset.maximumGuests);

    function updateQuote() {
        const guests = Number.parseInt(guestInput.value, 10);
        if (!guests || guests < 1 || guests > maximumGuests) {
            const message = guests > maximumGuests
                ? `Capacity limit is ${maximumGuests.toLocaleString('en-IN')} guests.`
                : 'Enter guest count to calculate an estimate.';
            quoteTotal.textContent = message;
            quoteNote.textContent = message;
            hallAmount.textContent = '-';
            cateringAmount.textContent = '-';
            summaryTotal.textContent = '-';
            return;
        }

        const hall = baseHallRate + Math.floor((guests - 1) / tierSize) * tierIncrement;
        const isCatered = cateringSelect.value === 'Vegetarian catering';
        const catering = isCatered ? guests * cateringRate : 0;
        const total = hall + catering;
        const formattedTotal = `₹${formatter.format(total)}`;

        quoteTotal.textContent = formattedTotal;
        quoteNote.textContent = `${guests.toLocaleString('en-IN')} guests · Hall ₹${formatter.format(hall)} · Catering ₹${formatter.format(catering)}`;
        hallAmount.textContent = `₹${formatter.format(hall)}`;
        cateringAmount.textContent = isCatered ? `₹${formatter.format(catering)}` : '₹0';
        summaryTotal.textContent = formattedTotal;
        paymentNote.textContent = cateringSelect.value === 'Discuss with management'
            ? 'Catering needs a separate quote. This estimate includes hall rental only. No payment is taken online.'
            : 'This is an estimate. The hall team confirms the final amount before accepting the reservation. No payment is taken online.';
    }

    guestInput.addEventListener('input', updateQuote);
    cateringSelect.addEventListener('change', updateQuote);
    updateQuote();
}