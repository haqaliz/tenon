class _Charges:
    def create(self, **kwargs):
        return kwargs

    def delete(self, id):
        return id


class StripeClient:
    def __init__(self):
        self.charges = _Charges()
