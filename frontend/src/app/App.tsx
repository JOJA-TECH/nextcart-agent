import { useMemo } from "react"
import { CheckoutPage } from "@/features/checkout/components/CheckoutPage"
import { HttpNextCartClient } from "@/shared/api/nextcart-client"
import { InstrumentedNextCartClient } from "@/features/recommendations/services/instrumented-client"
import { ApiActivityLogProvider, useApiActivityLog } from "@/shared/api/api-activity-log"

function AppRoot() {
  const { record } = useApiActivityLog()
  const client = useMemo(
    () => new InstrumentedNextCartClient(new HttpNextCartClient(), record),
    [record],
  )
  return <CheckoutPage client={client} />
}

export default function App() {
  return (
    <ApiActivityLogProvider>
      <AppRoot />
    </ApiActivityLogProvider>
  )
}
