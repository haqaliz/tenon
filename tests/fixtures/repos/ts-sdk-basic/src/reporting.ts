import { client } from "./billing";

client.charges.list({ limit: 10 });
