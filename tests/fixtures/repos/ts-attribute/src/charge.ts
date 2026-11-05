import Stripe from "stripe";

const charge = new Stripe("sk_test");

charge.amount;
