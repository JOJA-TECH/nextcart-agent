import { Table } from "@chakra-ui/react"
import type { ApiLogEntry } from "@/shared/api/api-activity-log"

export interface ApiLogTableProps {
  entries: ApiLogEntry[]
}

export function ApiLogTable({ entries }: ApiLogTableProps) {
  if (entries.length === 0) {
    return (
      <Table.Root size="sm" borderWidth="1px" rounded="md">
        <Table.Header>
          <Table.Row>
            <Table.ColumnHeader>Hora</Table.ColumnHeader>
            <Table.ColumnHeader>Método</Table.ColumnHeader>
            <Table.ColumnHeader>Endpoint</Table.ColumnHeader>
            <Table.ColumnHeader>Estado</Table.ColumnHeader>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          <Table.Row>
            <Table.Cell colSpan={4} color="fg.muted" textStyle="sm">
              Sin llamadas registradas todavía.
            </Table.Cell>
          </Table.Row>
        </Table.Body>
      </Table.Root>
    )
  }

  return (
    <Table.Root size="sm" borderWidth="1px" rounded="md">
      <Table.Header>
        <Table.Row>
          <Table.ColumnHeader>Hora</Table.ColumnHeader>
          <Table.ColumnHeader>Método</Table.ColumnHeader>
          <Table.ColumnHeader>Endpoint</Table.ColumnHeader>
          <Table.ColumnHeader>Estado</Table.ColumnHeader>
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {entries.map((entry) => (
          <Table.Row key={entry.id}>
            <Table.Cell fontFamily="mono" textStyle="xs">
              {entry.at}
            </Table.Cell>
            <Table.Cell textStyle="xs">{entry.method}</Table.Cell>
            <Table.Cell fontFamily="mono" textStyle="xs">
              {entry.path}
            </Table.Cell>
            <Table.Cell>
              <span
                style={{
                  color: entry.ok
                    ? "var(--chakra-colors-green-600)"
                    : "var(--chakra-colors-red-600)",
                  fontWeight: 600,
                }}
              >
                {entry.ok ? (entry.status ?? "OK") : (entry.status != null ? entry.status : "sin conexión")}
              </span>
              {entry.detail && (
                <span style={{ color: "var(--chakra-colors-fg-muted)" }}> — {entry.detail}</span>
              )}
            </Table.Cell>
          </Table.Row>
        ))}
      </Table.Body>
    </Table.Root>
  )
}
