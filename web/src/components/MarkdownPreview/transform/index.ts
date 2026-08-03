const processParts = (
  buffer,
  controller: TransformStreamDefaultController,
  splitOn,
) => {
  const parts = buffer.split(splitOn)

  parts.slice(0, -1).forEach((part) => {
    if (part.trim() !== '') {
      controller.enqueue(part)
    }
  })

  return parts[parts.length - 1]
}

export const splitStream = (
  splitOn,
): TransformStream<string, string> => {
  let buffer = ''

  return new TransformStream({
    transform(chunk, controller) {
      buffer += chunk
      buffer = processParts(
        buffer,
        controller,
        splitOn,
      )
    },

    flush(controller) {
      if (buffer.trim() !== '') {
        controller.enqueue(buffer)
      }
    },
  })
}