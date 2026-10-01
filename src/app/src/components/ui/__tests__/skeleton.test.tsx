import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Skeleton, SkeletonCard, SkeletonRegion, SkeletonText } from '..'

describe('Skeleton', () => {
  it('a região é aria-busy e tem UM só status, em sr-only', () => {
    const { container } = render(
      <SkeletonRegion label="Carregando projetos">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonText lines={3} />
      </SkeletonRegion>,
    )
    expect(container.firstElementChild).toHaveAttribute('aria-busy', 'true')
    const statuses = screen.getAllByRole('status')
    expect(statuses).toHaveLength(1)
    expect(statuses[0]).toHaveTextContent('Carregando projetos')
    expect(statuses[0]).toHaveClass('sr-only')
  })

  it('todos os blocos são aria-hidden', () => {
    const { container } = render(
      <>
        <Skeleton width="10px" height="4px" />
        <SkeletonText lines={2} />
        <SkeletonCard />
      </>,
    )
    const blocks = container.querySelectorAll('.skeleton')
    expect(blocks.length).toBeGreaterThan(3)
    for (const b of blocks) expect(b.closest('[aria-hidden="true"]')).not.toBeNull()
  })
})
