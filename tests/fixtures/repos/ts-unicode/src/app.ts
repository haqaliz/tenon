import Stripe from "stripe";

const client = new Stripe("sk_test");
const note = "café ☕"; client.charges.create({ amount: 1 });
