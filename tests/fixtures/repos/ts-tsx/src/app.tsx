import Stripe from "stripe";

const client = new Stripe("sk_test");

export function Billing() {
  return <button onClick={() => client.charges.create({ amount: 1 })}>Pay</button>;
}
