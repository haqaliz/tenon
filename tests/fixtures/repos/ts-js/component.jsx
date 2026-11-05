import Stripe from "stripe";

const client = new Stripe("sk_test");

export const Billing = () => <div>{client.charges.list({ limit: 1 })}</div>;
