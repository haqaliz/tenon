import stripe


def create_checkout(customer):
    return stripe.checkout.Session.create(
        customer=customer,
        payment_method_types=["card"],
        mode="payment",
    )
