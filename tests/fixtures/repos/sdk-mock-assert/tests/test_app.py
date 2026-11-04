import stripe


def test_create():
    stripe.checkout.Session.create.assert_called_once_with(
        payment_method_types=["card"]
    )
