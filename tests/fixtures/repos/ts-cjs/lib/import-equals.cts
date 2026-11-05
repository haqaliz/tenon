import stripe = require("stripe");

stripe.charges.create({ amount: 3 });
