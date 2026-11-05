const { Stripe } = require("stripe");

const client = new Stripe("sk_test");

client.charges.create({ amount: 2 });
