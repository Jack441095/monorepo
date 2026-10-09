// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import KennActionCard from '../KennActionCard.vue'

describe('KennActionCard dismissal', () => {
  const proposal = { action: 'set_mute', track_name: 'Bass', confirmation_token: 'held-token', before: false, after: true }

  it('shows a waiting state without Apply or a second Dismiss during revocation', () => {
    // Dismiss must await server revocation before the card claims no change was made.
    const wrapper = mount(KennActionCard, { props: { proposal, cardStatus: 'dismissing' } })
    expect(wrapper.text()).toContain('Dismissing...')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.kenn-action-card__btn--apply').exists()).toBe(false)
    expect(wrapper.find('.kenn-action-card__btn--reject').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Proposal Dismissed')
  })

  it('keeps a refused dismissal visible with Apply and Dismiss available again', () => {
    const wrapper = mount(KennActionCard, { props: { proposal, cardStatus: 'pending', errorMessage: 'Check Live before trying again.' } })
    expect(wrapper.text()).toContain('Check Live before trying again.')
    expect(wrapper.find('.kenn-action-card__btn--apply').exists()).toBe(true)
    expect(wrapper.find('.kenn-action-card__btn--reject').exists()).toBe(true)
  })
})

describe('KennActionCard on an applied undo', () => {
  const proposal = { action: 'set_volume', track_name: 'Synth', before: 0.6, after: 0.5 }

  it('offers no Undo, because undoing an undo would redo the change', () => {
    // Same bug as the recipe card (9 Oct 2026): the Undo button on an applied undo card reversed the undo.
    const original = mount(KennActionCard, { props: { proposal, cardStatus: 'applied' } })
    const undoCard = mount(KennActionCard, { props: { proposal, cardStatus: 'applied', undoable: false } })
    expect(original.find('.kenn-action-card__btn--undo').exists()).toBe(true)
    expect(undoCard.find('.kenn-action-card__btn--undo').exists()).toBe(false)
    expect(undoCard.text()).toContain('Readback Verified')
  })
})
