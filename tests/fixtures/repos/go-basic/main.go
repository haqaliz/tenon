package main

import (
    "github.com/stripe/stripe-go/v76"
    "github.com/stripe/stripe-go/v76/charge"
)

func main() {
    params := &stripe.ChargeParams{AmountCents: 100, Currency: "usd"}
    charge.New(params)
}
