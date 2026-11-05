import Stripe from "stripe";

const client = new Stripe("sk_test");
const payload = { amount: 1 };

client.charges.create({ ...payload });
client.charges.create(payload);
client.charges.create({ [key]: 1 });
client.charges.create({ amount: 1 });

const value = client[key];
client[key].create({ amount: 1 });
client["charges"].create({ amount: 1 });

const c = client;
const d = c;
