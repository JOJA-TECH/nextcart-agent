import { SimpleGrid } from "@chakra-ui/react"
import type { Recommendation } from "@/shared/api/contracts"
import { RecommendationCard } from "./RecommendationCard"

export interface RecommendationListProps {
  recommendations: Recommendation[]
  inventory: Record<string, boolean>
  acceptedIds: number[]
  rejectedIds: number[]
  ignoredIds: number[]
  busyProductId: number | null
  onAccept: (productId: number) => void
  onReject: (productId: number) => void
  onIgnore: (productId: number) => void
}

export function RecommendationList(props: RecommendationListProps) {
  const {
    recommendations,
    inventory,
    acceptedIds,
    rejectedIds,
    ignoredIds,
    busyProductId,
    onAccept,
    onReject,
    onIgnore,
  } = props

  return (
    <SimpleGrid columns={{ base: 1, md: 2, xl: 3 }} gap="3">
      {recommendations.map((rec) => (
        <RecommendationCard
          key={rec.product_id}
          productId={rec.product_id}
          score={rec.score}
          reason={rec.reason}
          source={rec.source}
          inventoryAvailable={inventory[String(rec.product_id)] ?? true}
          accepted={acceptedIds.includes(rec.product_id)}
          rejected={rejectedIds.includes(rec.product_id)}
          ignored={ignoredIds.includes(rec.product_id)}
          busy={busyProductId === rec.product_id}
          onAccept={() => onAccept(rec.product_id)}
          onReject={() => onReject(rec.product_id)}
          onIgnore={() => onIgnore(rec.product_id)}
        />
      ))}
    </SimpleGrid>
  )
}
