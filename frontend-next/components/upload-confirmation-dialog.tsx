"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { X, FileText, Globe, GlobeLock } from "lucide-react"

interface FileWithSettings {
  file: File
  webSearchEnabled: boolean
}

interface UploadConfirmationDialogProps {
  files: File[]
  onConfirm: (webSearchSettings: boolean[]) => void
  onCancel: () => void
}

export function UploadConfirmationDialog({
  files,
  onConfirm,
  onCancel
}: UploadConfirmationDialogProps) {
  const [fileSettings, setFileSettings] = React.useState<FileWithSettings[]>(() =>
    files.map(file => ({ file, webSearchEnabled: true }))
  )

  const toggleWebSearch = (index: number) => {
    setFileSettings(prev =>
      prev.map((item, idx) =>
        idx === index ? { ...item, webSearchEnabled: !item.webSearchEnabled } : item
      )
    )
  }

  const allWebSearchEnabled = fileSettings.every(item => item.webSearchEnabled)
  const someWebSearchEnabled = fileSettings.some(item => item.webSearchEnabled)

  const toggleAllWebSearch = () => {
    const newValue = !allWebSearchEnabled
    setFileSettings(prev =>
      prev.map(item => ({ ...item, webSearchEnabled: newValue }))
    )
  }

  const handleConfirm = () => {
    const webSearchSettings = fileSettings.map(item => item.webSearchEnabled)
    onConfirm(webSearchSettings)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getFileType = (file: File) => {
    const ext = file.name.split('.').pop()?.toUpperCase()
    if (file.type === 'application/pdf') return 'PDF'
    if (file.type.startsWith('text/')) return ext || 'TXT'
    return ext || 'FILE'
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <Card className="w-full max-w-2xl max-h-[80vh] overflow-hidden bg-white shadow-2xl border-none animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200 bg-gradient-to-r from-indigo-50 to-purple-50">
          <div className="flex-1">
            <h2 className="text-xl font-bold text-slate-900">Confirm File Upload</h2>
            <p className="text-sm text-slate-600 mt-1">
              Configure web search settings for each document
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Select All Checkbox */}
            <label className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-slate-300 hover:border-indigo-400 cursor-pointer transition-all">
              <input
                type="checkbox"
                checked={allWebSearchEnabled}
                ref={(input) => {
                  if (input) {
                    input.indeterminate = someWebSearchEnabled && !allWebSearchEnabled
                  }
                }}
                onChange={toggleAllWebSearch}
                className="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500 cursor-pointer"
              />
              <span className="text-sm font-medium text-slate-700 whitespace-nowrap">
                {allWebSearchEnabled ? 'Deselect All' : 'Select All'}
              </span>
            </label>
            <button
              onClick={onCancel}
              className="p-2 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <X className="h-5 w-5 text-slate-600" />
            </button>
          </div>
        </div>

        {/* File List */}
        <div className="p-6 overflow-y-auto max-h-[60vh]">
          <div className="space-y-3">
            {fileSettings.map((item, index) => (
              <Card
                key={index}
                className="p-4 border border-slate-200 hover:border-indigo-300 transition-all"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="mt-1 p-2 bg-indigo-100 rounded-lg">
                      <FileText className="h-5 w-5 text-indigo-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-slate-900 truncate">
                        {item.file.name}
                      </h3>
                      <p className="text-sm text-slate-500 mt-1">
                        {formatFileSize(item.file.size)} • {getFileType(item.file)}
                      </p>
                    </div>
                  </div>

                  {/* Web Search Toggle */}
                  <button
                    onClick={() => toggleWebSearch(index)}
                    className={`
                      flex items-center gap-2 px-4 py-2 rounded-lg border-2 transition-all font-medium text-sm
                      ${
                        item.webSearchEnabled
                          ? "bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-100"
                          : "bg-slate-100 text-slate-600 border-slate-300 hover:bg-slate-200"
                      }
                    `}
                  >
                    {item.webSearchEnabled ? (
                      <>
                        <Globe className="h-4 w-4" />
                        Web Search: ON
                      </>
                    ) : (
                      <>
                        <GlobeLock className="h-4 w-4" />
                        Web Search: OFF
                      </>
                    )}
                  </button>
                </div>

                {/* Description */}
                <div className="mt-3 ml-14 text-xs text-slate-500">
                  {item.webSearchEnabled ? (
                    <p>
                      ✓ Facts will be verified using web search for accuracy
                    </p>
                  ) : (
                    <p>
                      ✗ Facts will be extracted but not verified via web search
                    </p>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-slate-200 bg-slate-50">
          <div className="text-sm text-slate-600">
            {fileSettings.filter(f => f.webSearchEnabled).length} of {files.length} with web search enabled
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={onCancel}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirm}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              Upload {files.length} {files.length === 1 ? "File" : "Files"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
