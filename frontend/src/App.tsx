import { useState } from 'react'
import { AppLayout, type TabKey } from '@/components/layout/AppLayout'
import { ItemsPage } from '@/features/items/ItemsPage'
import { AIPage } from '@/features/ai/AIPage'
import { UploadsPage } from '@/features/uploads/UploadsPage'

export function App() {
  const [currentTab, setCurrentTab] = useState<TabKey>('items')

  return (
    <AppLayout currentTab={currentTab} onSelectTab={setCurrentTab}>
      {currentTab === 'items' && <ItemsPage />}
      {currentTab === 'ai' && <AIPage />}
      {currentTab === 'uploads' && <UploadsPage />}
    </AppLayout>
  )
}
