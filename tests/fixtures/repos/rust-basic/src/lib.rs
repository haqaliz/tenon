use stripe::{Charge, CreateCharge};

pub fn create_charge(amount: i64) -> Charge {
    let params = CreateCharge {
        amount_cents: amount,
        currency: "usd",
    };

    Charge::create(&params)
}
