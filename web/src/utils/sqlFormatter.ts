export const formatSQL = (sql: string): string => {
  if (!sql) return ''
  
  let formatted = sql.trim()
  
  // Standardize spaces
  formatted = formatted.replace(/\s+/g, ' ')
  
  // Keywords to uppercase (basic set)
  const keywords = [
    'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'GROUP BY', 'ORDER BY', 
    'LIMIT', 'OFFSET', 'HAVING', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 
    'INNER JOIN', 'OUTER JOIN', 'UNION', 'VALUES', 'INSERT INTO', 
    'UPDATE', 'DELETE', 'CREATE TABLE', 'DROP TABLE', 'ALTER TABLE'
  ]
  
  keywords.forEach(kw => {
    const regex = new RegExp(`\\b${kw}\\b`, 'gi')
    formatted = formatted.replace(regex, kw)
  })
  
  // Add newlines
  const newlines = [
    'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'LIMIT', 
    'HAVING', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 
    'OUTER JOIN', 'UNION', 'VALUES', 'INSERT INTO', 'UPDATE', 'DELETE'
  ]
  
  newlines.forEach(kw => {
    const regex = new RegExp(`\\b${kw}\\b`, 'g')
    formatted = formatted.replace(regex, `\n${kw}`)
  })
  
  // Fix comma spacing
  formatted = formatted.replace(/\s*,\s*/g, ',\n  ')
  
  // Indentation for keywords (simple)
  // This is hard to do perfectly with regex, but let's try basic
  // We already added \n before keywords.
  // Maybe add indentation to lines that don't start with a main keyword?
  
  const lines = formatted.split('\n')
  const indentedLines = lines.map(line => {
    const trimmed = line.trim()
    if (!trimmed) return ''
    
    // If line starts with one of the main keywords, keep it (maybe indent 0 or 2?)
    // If not, indent it
    const startsWithKeyword = newlines.some(kw => trimmed.startsWith(kw))
    if (startsWithKeyword) {
      return trimmed
    } else {
      return '  ' + trimmed
    }
  })
  
  return indentedLines.join('\n').trim()
}
