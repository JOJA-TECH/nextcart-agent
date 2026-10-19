import type { BoxProps } from "@chakra-ui/react"
import { Box, Center, Spinner, Stack, Text } from "@chakra-ui/react"

interface StateBoxProps extends BoxProps {
  title: string
  description?: string
}

function StateBox({ title, description, ...rest }: StateBoxProps) {
  return (
    <Center py="10" px="4" {...rest}>
      <Stack gap="2" textAlign="center">
        <Text fontWeight="semibold" color="fg">
          {title}
        </Text>
        {description && (
          <Text textStyle="sm" color="fg.muted" maxW="prose">
            {description}
          </Text>
        )}
      </Stack>
    </Center>
  )
}

export function LoadingState({ title = "Consultando el backend…" }: { title?: string }) {
  return (
    <Center py="10" gap="3">
      <Spinner size="sm" color="blue.solid" />
      <Text textStyle="sm" color="fg.muted">
        {title}
      </Text>
    </Center>
  )
}

export function EmptyState({ title, description }: StateBoxProps) {
  return <StateBox title={title} description={description} />
}

export function ErrorState({ title, description }: StateBoxProps) {
  return (
    <Box
      rounded="lg"
      borderWidth="1px"
      borderColor="red.emphasized"
      bg="red.subtle"
    >
      <StateBox title={title} description={description} color="red.fg" />
    </Box>
  )
}
