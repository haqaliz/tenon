import Stripe from "stripe";

const client = new Stripe("sk_test");

client.charges.get("ch_1");
client.charges.list({ limit: 10 });
