import { useState } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  question: string
  onAnswer: (text: string) => Promise<void>
}

export function ClarifyingQuestion({ question, onAnswer }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const submit = async () => {
    if (!text.trim()) return
    setSending(true)
    await onAnswer(text.trim())
    setSending(false)
  }
  return (
    <Alert className="border-primary/50">
      <AlertTitle>Une précision est nécessaire</AlertTitle>
      <AlertDescription className="space-y-3">
        <p className="text-foreground">{question}</p>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <Input
            aria-label="Votre réponse"
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            autoFocus
          />
          <Button type="submit" disabled={sending || !text.trim()}>
            Répondre
          </Button>
        </form>
      </AlertDescription>
    </Alert>
  )
}
