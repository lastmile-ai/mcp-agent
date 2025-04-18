## Flight Cancellation Policy

1. Confirm which flight the customer is asking to cancel.

   1a) If the customer is asking about the same flight, proceed to next step.

   1b) If the customer is not, call 'escalate_to_agent' function.

2. Confirm if the customer wants a refund or flight credits.

3. If the customer wants a refund follow step 3a). If the customer wants flight credits move to step 4.

   3a) Call the initiate_refund function.

   3b) Inform the customer that the refund will be processed within 3-5 business days.

4. If the customer wants flight credits, call the initiate_flight_credits function.

   4a) Inform the customer that the flight credits will be available in the next 15 minutes.

5. If the customer has no further questions, call the case_resolved function.
