import Stripe from "stripe";
import * as stripe from "stripe";

const client = new Stripe("sk_test");
const direct = Stripe;
const charges = stripe.charges;
const { balance, charges: renamed } = stripe;

client.amount;
direct.amount;
charges.create({ amount: 1 });
balance.retrieve();
renamed.create({ amount: 2 });

const c = client;
const d = c;

const { account: { id } } = stripe;

let late = new Stripe();
late = other;
late.charges.create({ amount: 9 });
