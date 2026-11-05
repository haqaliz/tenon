import Stripe from "stripe";

export const client = new Stripe("sk_test");

client.charges.create({ amount: 100, currency: "usd" });
client.charges.delete("ch_1");
