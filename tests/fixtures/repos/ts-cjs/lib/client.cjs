const stripe = require("stripe");

stripe.charges.create({ amount: 1 });
