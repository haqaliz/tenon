import { charges } from "stripe";

charges.create({ currency: "usd" });
