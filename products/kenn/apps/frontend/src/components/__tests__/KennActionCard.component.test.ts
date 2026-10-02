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
