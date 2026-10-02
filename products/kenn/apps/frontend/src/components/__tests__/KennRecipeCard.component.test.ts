// @vitest-environment happy-dom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KennRecipeCard from '../KennRecipeCard.vue'
import type { KennActionProposal } from '../../api/kenn'

// Built from what handle_command actually returned for "turn the hats down 3 dB and the kick up 2 dB" on
// FakeLiveBackend on 2026-09-30, so this is the shape the card has to render rather than an idealised one.
const recipe: KennActionProposal = {
  schema: 'kenn.ableton_recipe_proposal.v1',
  action: 'recipe',
  operation: 'recipe',
  target: 'ableton_recipe',
  confirmation_token: 'recipe-7cdd85d0',
  steps: [
    {
      action_id: 'action-69422e77',
      action: 'set_volume',
      operation: 'set_volume',
      track_index: 2,
      track_name: 'Hi-Hats',
      before: 0.5,
      after: 0.472,
      before_db: -14,
      after_db: -17,
      unit: 'normalized',
      requires_confirmation: true,
    },
    {
      action_id: 'action-2b81c4aa',
      action: 'set_volume',
      operation: 'set_volume',
      track_index: 0,
      track_name: 'Kick',
      before: 0.5,
      after: 0.524,
      before_db: -14,
      after_db: -12,
      unit: 'normalized',
      requires_confirmation: true,
    },
  ],
}

describe('KennRecipeCard', () => {
  it('names the track on every step', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).toContain('Hi-Hats')
    expect(wrapper.text()).toContain('Kick')
  })

  it('never renders the bare "Track " label the single-action card produced', () => {
    // This is the defect it exists for: a recipe carries no track_name of its own, so the old card printed
    // `track_name || "Track " + (track_index != null ? ... : '')` and got an empty track.
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).not.toMatch(/Track\s*$|Track\s{2,}/m)
    expect(wrapper.text()).not.toContain('Track 1')
  })

  it('shows how many changes there are', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).toContain('2 changes')
    expect(wrapper.findAll('li')).toHaveLength(2)
  })

  it('says nothing has changed yet before Apply', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'pending' } })
    expect(wrapper.text()).toContain('Nothing has changed yet')
  })

  it('applies the whole plan in one action, because a step cannot be applied on its own', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'requires_confirmation' } })
    const apply = wrapper.find('.kenn-recipe-card__btn--apply')
    expect(apply.exists()).toBe(true)
    expect(apply.text()).toContain('Apply all 2')
    apply.trigger('click')
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })

  it('offers no Apply once the plan is applied', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'applied' } })
    expect(wrapper.find('.kenn-recipe-card__btn--apply').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Nothing has changed yet')
  })

  it('waits with disabled dismissal and no Apply until token revocation finishes', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'dismissing' } })
    expect(wrapper.text()).toContain('Dismissing...')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.kenn-recipe-card__btn--apply').exists()).toBe(false)
    expect(wrapper.find('.kenn-recipe-card__btn--reject').exists()).toBe(false)
  })

  it('falls back to a track index when a step has no name', () => {
    const unnamed: KennActionProposal = {
      ...recipe,
      steps: [{ action: 'set_mute', operation: 'set_mute', track_index: 3 }],
    }
    expect(mount(KennRecipeCard, { props: { proposal: unnamed } }).text()).toContain('Track 4')
  })

  it('says the value is unconfirmed rather than showing a blank transition', () => {
    const noDb: KennActionProposal = {
      ...recipe,
      steps: [{ action: 'set_mute', operation: 'set_mute', track_name: 'Kick' }],
    }
    expect(mount(KennRecipeCard, { props: { proposal: noDb } }).text()).toContain('value to be confirmed')
  })

  it('renders a label rather than a raw action name', () => {
    expect(mount(KennRecipeCard, { props: { proposal: recipe } }).text()).toContain('VOLUME')
    expect(mount(KennRecipeCard, { props: { proposal: recipe } }).text()).not.toContain('set_volume')
  })

  it('surfaces an error rather than swallowing it', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'error', errorMessage: 'boom' } })
    expect(wrapper.text()).toContain('boom')
  })
})
