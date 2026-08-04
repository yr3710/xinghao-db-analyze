export type HistoryStreamReader
  = ReadableStreamDefaultReader<Uint8Array>

export function parseStoredAnswer(value: unknown): string {
  if (!value) {
    return ''
  }

  if (typeof value === 'object') {
    const stored = value as any
    return stored.data?.content ?? ''
  }

  if (typeof value !== 'string') {
    return ''
  }

  try {
    const stored = JSON.parse(value)
    return stored.data?.content ?? ''
  }
  catch {
    return value
  }
}

export function createHistoryReader(
  answer: string,
): HistoryStreamReader {
  const encoder = new TextEncoder()
  const historyData = {
    messageType: 'continue',
    content: answer,
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode(`${JSON.stringify(historyData)}\n`),
      )
      controller.close()
    },
  })

  return stream.getReader()
}
