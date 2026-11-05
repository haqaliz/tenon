import Stripe from "stripe";

import { send } from "./format";

const client = new Stripe("sk_test");

client.charges.create({ amount: 100 });
send({ amount: 1 });
