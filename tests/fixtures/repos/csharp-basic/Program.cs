using Stripe;
using Stripe.Services;

namespace Billing;

public static class Program
{
    public static void Charge()
    {
        var options = new ChargeCreateOptions { AmountCents = 100, Currency = "usd" };
        var service = new ChargeService();
        service.Create(options);
    }
}
