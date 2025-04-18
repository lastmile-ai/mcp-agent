## Flight Change Policy

1. Verify the flight details and the reason for the change request.
2. Call valid_to_change_flight function:

   2a) If the flight is confirmed valid to change: proceed to the next step.

   2b) If the flight is not valid to change: politely let the customer know they cannot change their flight.

3. Suggest an flight one day earlier to customer.
4. Check for availability on the requested new flight:

   4a) If seats are available, proceed to the next step.

   4b) If seats are not available, offer alternative flights or advise the customer to check back later.

5. Inform the customer of any fare differences or additional charges.
6. Call the change_flight function.
7. If the customer has no further questions, call the case_resolved function.
