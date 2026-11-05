import Stripe from "stripe";

const sdk = await import("stripe");

sdk.charges.create({ amount: 1 });
